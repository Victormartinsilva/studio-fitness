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
