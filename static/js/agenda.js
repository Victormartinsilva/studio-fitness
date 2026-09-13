/*
 * Grade diária da agenda: ao abrir a página, rola até o ponto relevante do
 * dia — a "linha do agora" (hoje, dentro do expediente) ou, na falta dela,
 * o primeiro horário ocupado do dia (`grade.py` calcula os dois em
 * `linha_agora_top`/`scroll_inicial_top` e expõe via `data-*` no `.grade`).
 * Sem isso a página sempre abre no topo do expediente (07:00), bem acima
 * da dobra em qualquer dia com sessão marcada.
 *
 * JS vanilla, sem dependências, sem `innerHTML`.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // ---- Sincroniza o scroll horizontal dos cabeçalhos de equipamento
    // (`.grade-cabecas-lista`, linha sticky fora de `.colunas`) com o
    // scroll horizontal real de `.grade .colunas`. Um único sentido
    // (colunas -> cabeçalhos) é suficiente: o usuário nunca arrasta a
    // linha de cabeçalhos diretamente (ela nem mostra barra de rolagem),
    // então não há risco de loop de eventos entre os dois listeners.
    const colunas = document.getElementById("grade-colunas");
    const cabecasLista = document.getElementById("grade-cabecas-lista");
    if (colunas && cabecasLista) {
      colunas.addEventListener(
        "scroll",
        function () {
          cabecasLista.scrollLeft = colunas.scrollLeft;
        },
        { passive: true }
      );
    }

    // ---- Bottom sheets das vagas consolidadas (mobile) e dos blocos de
    // sessão (Etapa 2c-ii): cada gatilho com `data-abre-dialog` abre o
    // `<dialog class="folha-inferior">` correspondente, já renderizado
    // pelo servidor — nada de montar conteúdo dinamicamente em JS. Fecha
    // no botão "×" ou clicando fora (no ::backdrop, truque padrão de
    // `<dialog>`: o clique no backdrop chega com `target` sendo o próprio
    // elemento `<dialog>`).
    //
    // O gatilho é um `<button type="button">` (vagas consolidadas, não
    // navega) OU um `<a href="...">` (blocos de sessão — link de fallback
    // pra página de detalhe sem JS). `preventDefault()` só é chamado
    // DEPOIS de confirmar que o dialog existe e `showModal()` funcionou:
    // inofensivo pro `<button>` (que não navega de qualquer forma) e
    // essencial pro `<a>`, mas sem impedir a navegação de fallback se o
    // dialog não existir ou `showModal()` falhar por algum motivo.
    document.querySelectorAll("[data-abre-dialog]").forEach(function (gatilho) {
      gatilho.addEventListener("click", function (evento) {
        const alvo = document.getElementById(gatilho.dataset.abreDialog);
        if (alvo && typeof alvo.showModal === "function") {
          alvo.showModal();
          evento.preventDefault();
        }
      });
    });
    document.querySelectorAll("dialog.folha-inferior").forEach(function (folha) {
      const fechar = folha.querySelector(".folha-fechar");
      if (fechar) {
        fechar.addEventListener("click", function () {
          folha.close();
        });
      }
      folha.addEventListener("click", function (evento) {
        if (evento.target === folha) {
          folha.close();
        }
      });
    });

    // ---- Busca de aluno sem <select> nativo (Etapa 3a, formulário de
    // agendar): o campo real do form (`AgendarForm.aluno`) continua sendo
    // um `ModelChoiceField` normal por baixo — só a aparência muda. O
    // servidor renderiza `#id_aluno` como `<input type="hidden">` e
    // `#lista-alunos` como uma `<datalist>` com todos os alunos ativos
    // (`<option value="Nome" data-id="123">`); `#busca-aluno` é o
    // `<input type="text">` visível que o usuário digita/filtra (o próprio
    // navegador filtra as opções da datalist, sem fetch nenhum). Não existe
    // evento nativo "selecionou da datalist" em JS puro — detectamos a
    // seleção comparando o texto digitado com o `value` exato de alguma
    // `<option>` e copiamos o `data-id` correspondente pro hidden. Se não
    // bater com nada (ainda digitando, ou nome inválido), o hidden fica
    // vazio, e a validação do `ModelChoiceField` falha do mesmo jeito que já
    // falha hoje pra um campo obrigatório vazio.
    const buscaAluno = document.getElementById("busca-aluno");
    const listaAlunos = document.getElementById("lista-alunos");
    const alunoValor = document.getElementById("id_aluno");
    if (buscaAluno && listaAlunos && alunoValor) {
      const opcoes = Array.from(listaAlunos.options);

      // Reabrindo o formulário já com um aluno definido (vaga clicada com
      // `?aluno=<id>` na grade, ou reexibição após erro de validação do
      // agendamento): o hidden já vem preenchido com o ID pelo servidor,
      // mas o input de busca visível começa vazio — preenche o nome
      // correspondente procurando a option com esse `data-id`.
      if (alunoValor.value) {
        const opcaoAtual = opcoes.find(function (opcao) {
          return opcao.dataset.id === alunoValor.value;
        });
        if (opcaoAtual) {
          buscaAluno.value = opcaoAtual.value;
        }
      }

      const sincronizarComABusca = function () {
        const opcaoSelecionada = opcoes.find(function (opcao) {
          return opcao.value === buscaAluno.value;
        });
        alunoValor.value = opcaoSelecionada ? opcaoSelecionada.dataset.id : "";
      };
      buscaAluno.addEventListener("input", sincronizarComABusca);
      buscaAluno.addEventListener("change", sincronizarComABusca);
    }

    // ---- Fluxo em passos do formulário de agendar (Etapa 3b): progressive
    // enhancement puro. Sem JS, todos os `fieldset.passo-agendar` abaixo
    // ficam visíveis ao mesmo tempo (comportamento padrão do HTML — só o JS
    // ESCONDE quando roda) e o formulário continua sendo UM `<form>` só, com
    // todos os campos reais, que funciona exatamente como antes via POST
    // direto. Com JS: agrupa visualmente em passos (aluno → tipo → dia e
    // horário → confirmar), busca horários livres via fetch em
    // `/agenda/vagas.json` e deixa o botão final sempre alcançável.
    const formAgendar = document.getElementById("form-agendar");
    const passos = formAgendar ? Array.from(formAgendar.querySelectorAll(".passo-agendar")) : [];
    if (formAgendar && passos.length && buscaAluno && alunoValor) {
      const cabecalho = document.getElementById("passos-cabecalho");
      const indicador = document.getElementById("passos-indicador");
      const botaoVoltar = document.getElementById("passo-voltar");
      const camposFallback = formAgendar.querySelector(".campos-fallback");
      const campoTipo = document.getElementById("id_tipo");
      const campoData = document.getElementById("id_data");
      const campoProfessor = document.getElementById("id_professor");
      const campoEquipamento = document.getElementById("id_equipamento");
      const campoHoraInicio = document.getElementById("id_hora_inicio");
      const horariosContainer = document.getElementById("horarios-disponiveis");
      const chipsPeriodo = Array.from(document.querySelectorAll("#periodo-chips .chip"));
      const resumoConfirmar = document.getElementById("resumo-confirmar");

      let passoAtual = 1;
      let periodoEscolhido = null;

      const textoSelecionado = function (select) {
        if (!select || select.selectedIndex < 0) {
          return "";
        }
        const opcao = select.options[select.selectedIndex];
        return opcao ? opcao.textContent.trim() : "";
      };

      const montarResumo = function () {
        if (!resumoConfirmar) {
          return;
        }
        resumoConfirmar.textContent = "";
        [
          ["Aluno", buscaAluno.value],
          ["Tipo de sessão", textoSelecionado(campoTipo)],
          ["Professor", textoSelecionado(campoProfessor)],
          ["Dia", campoData ? campoData.value : ""],
          ["Horário", campoHoraInicio ? campoHoraInicio.value : ""],
          ["Equipamento", textoSelecionado(campoEquipamento) || "Nenhum"],
        ].forEach(function (linha) {
          const item = document.createElement("p");
          item.className = "resumo-linha";
          const rotulo = document.createElement("strong");
          rotulo.textContent = linha[0] + ": ";
          item.appendChild(rotulo);
          item.appendChild(document.createTextNode(linha[1] || "—"));
          resumoConfirmar.appendChild(item);
        });
      };

      const mostrarPasso = function (numero) {
        passoAtual = numero;
        passos.forEach(function (fieldset) {
          fieldset.hidden = String(numero) !== fieldset.dataset.passo;
        });
        cabecalho.hidden = false;
        indicador.textContent = "Passo " + numero + " de " + passos.length;
        botaoVoltar.hidden = numero === 1;
        if (numero === 3) {
          buscarHorarios();
        } else if (numero === 4) {
          montarResumo();
        }
      };

      function buscarHorarios() {
        if (!horariosContainer || !campoTipo || !campoData || !campoTipo.value || !campoData.value) {
          return;
        }
        horariosContainer.textContent = "";
        const carregando = document.createElement("p");
        carregando.className = "sub";
        carregando.textContent = "Buscando horários livres...";
        horariosContainer.appendChild(carregando);

        const parametros = new URLSearchParams({ tipo: campoTipo.value, data: campoData.value });
        if (campoProfessor && campoProfessor.value) {
          parametros.set("professor", campoProfessor.value);
        }
        if (campoEquipamento && campoEquipamento.value) {
          parametros.set("equipamento", campoEquipamento.value);
        }
        if (periodoEscolhido) {
          parametros.set("periodo", periodoEscolhido);
        }

        fetch("/agenda/vagas.json?" + parametros.toString())
          .then(function (resposta) {
            return resposta.json();
          })
          .then(function (dados) {
            horariosContainer.textContent = "";
            if (!dados.vagas || !dados.vagas.length) {
              const vazio = document.createElement("p");
              vazio.className = "sub";
              vazio.textContent = "Nenhum horário livre para esse tipo/dia — tente outro período ou outro dia.";
              horariosContainer.appendChild(vazio);
              return;
            }
            dados.vagas.forEach(function (vaga) {
              const chip = document.createElement("button");
              chip.type = "button";
              chip.className = "sugestao-item";

              const quando = document.createElement("span");
              quando.className = "quando";
              quando.textContent = vaga.inicio + "–" + vaga.fim;
              chip.appendChild(quando);

              const onde = document.createElement("span");
              onde.className = "onde";
              onde.textContent =
                vaga.professor_nome + (vaga.equipamento_nome ? " · " + vaga.equipamento_nome : "");
              chip.appendChild(onde);

              chip.addEventListener("click", function () {
                if (campoProfessor) {
                  campoProfessor.value = String(vaga.professor_id);
                }
                if (campoEquipamento) {
                  campoEquipamento.value = vaga.equipamento_id ? String(vaga.equipamento_id) : "";
                }
                if (campoHoraInicio) {
                  campoHoraInicio.value = vaga.inicio;
                }
                mostrarPasso(4);
              });

              horariosContainer.appendChild(chip);
            });
          })
          .catch(function () {
            horariosContainer.textContent = "";
            const erro = document.createElement("p");
            erro.className = "sub";
            erro.textContent = "Não foi possível buscar horários livres agora. Tente novamente.";
            horariosContainer.appendChild(erro);
          });
      }

      // Só esconde os campos reais de professor/hora/equipamento (fallback
      // sem JS) depois de confirmar que o JS está mesmo ativo — escolher um
      // chip de horário acima preenche os três de uma vez.
      if (camposFallback) {
        camposFallback.hidden = true;
      }

      formAgendar.querySelectorAll(".passo-proximo").forEach(function (botao) {
        botao.addEventListener("click", function () {
          const passoDoBotao = Number(botao.closest(".passo-agendar").dataset.passo);
          if (passoDoBotao === 1 && !alunoValor.value) {
            buscaAluno.reportValidity();
            return;
          }
          mostrarPasso(passoDoBotao + 1);
        });
      });

      if (botaoVoltar) {
        botaoVoltar.addEventListener("click", function () {
          mostrarPasso(Math.max(1, passoAtual - 1));
        });
      }

      chipsPeriodo.forEach(function (chip) {
        chip.addEventListener("click", function () {
          const jaAtivo = chip.classList.contains("ativo");
          chipsPeriodo.forEach(function (c) {
            c.classList.remove("ativo");
          });
          periodoEscolhido = jaAtivo ? null : chip.dataset.periodo;
          if (!jaAtivo) {
            chip.classList.add("ativo");
          }
          buscarHorarios();
        });
      });

      if (campoTipo) {
        campoTipo.addEventListener("change", buscarHorarios);
      }
      if (campoData) {
        campoData.addEventListener("change", buscarHorarios);
      }

      mostrarPasso(1);
      // Vindo de uma vaga clicada na grade (tipo/data já preenchidos via
      // querystring): busca os horários livres já no carregamento, antes
      // mesmo de o usuário alcançar o passo 3.
      if (campoTipo && campoData && campoTipo.value && campoData.value) {
        buscarHorarios();
      }
    }

    // ---- FAB da agenda (Etapa 2e): a opção "Perguntar ao assistente"
    // (`.fab-abre-assistente`) não abre painel nenhum por conta própria —
    // ela só dispara um clique programático no botão original do
    // assistente (`#assistente-botao`, escondido visualmente só nesta
    // página via CSS, ver `.pagina-agenda .assistente-botao` em app.css),
    // reaproveitando 100% a lógica de abrir/fechar já existente em
    // `assistente.js`. Também fecha o `<details class="fab-agenda">` pra
    // não deixar o menu aberto por cima do painel/página.
    const fabAgenda = document.querySelector(".fab-agenda");
    document.querySelectorAll(".fab-abre-assistente").forEach(function (opcao) {
      opcao.addEventListener("click", function () {
        if (fabAgenda) {
          fabAgenda.open = false;
        }
        document.getElementById("assistente-botao")?.click();
      });
    });

    // ---- Swipe horizontal na linha do tempo (Etapa 2e): arrastar pra
    // esquerda/direita na lista vertical de sessões (`.linha-tempo`) troca
    // de dia, como um atalho a mais além dos links ‹/› do cabeçalho. Só
    // aqui — nunca em `.grade .colunas` nem `.faixa-dias`, que já têm
    // scroll horizontal próprio (arrastar ali precisa continuar rolando as
    // colunas/dias, não trocar de dia). Passivo e sem `preventDefault` em
    // nenhum momento, pra não brigar com o scroll vertical nativo da
    // página. `data-dia-anterior`/`data-dia-seguinte` (ISO, ex. "2026-09-11")
    // vêm do próprio elemento, preenchidos pelo template com os mesmos dias
    // já usados nos links ‹/› do cabeçalho.
    const linhaTempo = document.querySelector(".linha-tempo");
    if (linhaTempo) {
      let toqueInicioX = null;
      let toqueInicioY = null;

      linhaTempo.addEventListener(
        "touchstart",
        function (evento) {
          const toque = evento.touches[0];
          toqueInicioX = toque.clientX;
          toqueInicioY = toque.clientY;
        },
        { passive: true }
      );

      linhaTempo.addEventListener(
        "touchend",
        function (evento) {
          if (toqueInicioX === null) {
            return;
          }
          const toque = evento.changedTouches[0];
          const deltaX = toque.clientX - toqueInicioX;
          const deltaY = toque.clientY - toqueInicioY;
          toqueInicioX = null;
          toqueInicioY = null;

          const LIMIAR_PX = 60;
          if (Math.abs(deltaX) < LIMIAR_PX || Math.abs(deltaX) <= Math.abs(deltaY)) {
            return;
          }

          const dia = deltaX > 0 ? linhaTempo.dataset.diaAnterior : linhaTempo.dataset.diaSeguinte;
          if (dia) {
            window.location.href = "?data=" + dia + "#dia-atual";
          }
        },
        { passive: true }
      );
    }

    // ---- Auto-scroll ao abrir a página: rola até a "linha do agora" ou,
    // na falta dela, o primeiro horário ocupado do dia (`grade.py` calcula
    // os dois em `linha_agora_top`/`scroll_inicial_top` e expõe via
    // `data-*` no `.grade`). Sem isso a página sempre abre no topo do
    // expediente (07:00), bem acima da dobra em qualquer dia com sessão
    // marcada.
    const grade = document.querySelector(".grade");
    const pista = grade ? grade.querySelector(".pista") : null;
    if (!grade || !pista) {
      return;
    }

    const alvoTexto = grade.dataset.linhaAgoraTop || grade.dataset.scrollInicialTop;
    if (!alvoTexto) {
      return;
    }

    const alvoPx = parseFloat(alvoTexto);
    if (isNaN(alvoPx)) {
      return;
    }

    // Posição absoluta na página = topo da pista + posição do alvo dentro
    // dela, descontando o `.topbar` fixo, a faixa de dias e a linha de
    // cabeçalhos sticky (`.faixa-dias`, `.grade-cabecas` — todos ficam por
    // cima do conteúdo depois de rolar) mais uma margem extra pra não colar
    // em nenhum dos três.
    // `.faixa-dias` só é sticky no mobile (`@media (max-width: 599px)` em
    // app.css) — no desktop ela rola normalmente com o resto da página, por
    // isso só desconta a altura dela quando o CSS realmente a tornou
    // sticky (checar a posição computada em vez de reimplementar aqui o
    // breakpoint que já existe no CSS).
    const topbar = document.querySelector(".topbar");
    const faixaDias = document.querySelector(".faixa-dias");
    const gradeCabecas = document.querySelector(".grade-cabecas");
    const alturaTopbar = topbar ? topbar.getBoundingClientRect().height : 0;
    const alturaFaixaDias =
      faixaDias && window.getComputedStyle(faixaDias).position === "sticky"
        ? faixaDias.getBoundingClientRect().height
        : 0;
    const alturaCabecas = gradeCabecas ? gradeCabecas.getBoundingClientRect().height : 0;
    const margem = 16;

    const destino =
      pista.getBoundingClientRect().top +
      window.pageYOffset +
      alvoPx -
      alturaTopbar -
      alturaFaixaDias -
      alturaCabecas -
      margem;

    // Duplo rAF (roda só depois que o navegador terminou de pintar o
    // primeiro frame): os links da página navegam com "#dia-atual" na URL
    // (troca de dia, faixa de dias, meses) pra rolar a faixa de dias
    // horizontalmente até o chip do dia selecionado — isso também dispara
    // rolagem vertical nativa do navegador até esse mesmo elemento, que
    // concorre com este scroll. Rodar depois do primeiro paint garante que
    // este scroll (o que realmente importa: o horário do dia) vença por
    // último, de forma consistente entre navegadores, sem atrasar
    // perceptivelmente o que o usuário vê.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        window.scrollTo(0, Math.max(destino, 0));
      });
    });
  });
})();
