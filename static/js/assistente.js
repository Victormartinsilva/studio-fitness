/*
 * Chat do assistente da agenda: abre/fecha o painel, manda mensagens pro
 * backend via fetch e renderiza resposta + cartões de confirmação.
 *
 * Regra de segurança: texto vindo do servidor/modelo SEMPRE via
 * `textContent`, nunca `innerHTML` — o texto do LLM não é confiável.
 *
 * JS vanilla, sem dependências.
 */
(function () {
  "use strict";

  function getCookie(nome) {
    const alvo = nome + "=";
    const partes = document.cookie.split(";");
    for (let parte of partes) {
      parte = parte.trim();
      if (parte.indexOf(alvo) === 0) {
        return decodeURIComponent(parte.slice(alvo.length));
      }
    }
    return "";
  }

  function chamarApi(url, corpo) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify(corpo),
    }).then(function (resposta) {
      return resposta.json().catch(function () {
        return {};
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const botao = document.getElementById("assistente-botao");
    const painel = document.getElementById("assistente-painel");
    const fechar = document.getElementById("assistente-fechar");
    const form = document.getElementById("assistente-form");
    const input = document.getElementById("assistente-input");
    const enviar = document.getElementById("assistente-enviar");
    const historico = document.getElementById("assistente-historico");
    const chips = document.querySelectorAll(".assistente-sugestao");

    if (!botao || !painel || !form || !input || !historico) {
      return;
    }

    // Altura do painel no mobile: `100dvh` (CSS) já cobre a maior parte dos
    // casos, mas o Safari iOS às vezes não reduz a viewport dinâmica quando
    // o teclado abre — corrige na mão com `visualViewport.resize`. No
    // desktop o painel tem posição/tamanho fixos (CSS, `@media min-width:
    // 900px`), então só ajusta abaixo do breakpoint.
    function ajustarAlturaPainel() {
      if (!window.visualViewport) {
        return;
      }
      const mobile = window.matchMedia("(max-width: 899px)").matches;
      painel.style.height = mobile && !painel.hidden ? window.visualViewport.height + "px" : "";
    }

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", ajustarAlturaPainel);
    }

    // Histórico da sessão (guardado no backend por `conversa.py`) só é
    // buscado uma vez por carregamento de página, na primeira vez que o
    // painel abre — assim, ao navegar pra outra página e reabrir o chat, as
    // últimas mensagens reaparecem em vez do painel começar vazio de novo.
    let historicoCarregado = false;
    function carregarHistorico() {
      if (historicoCarregado) {
        return;
      }
      historicoCarregado = true;
      fetch("/assistente/historico")
        .then(function (resposta) {
          return resposta.json();
        })
        .then(function (dados) {
          (dados.mensagens || []).forEach(function (msg) {
            adicionarMensagem(msg.content, msg.role === "user" ? "usuario" : "assistente");
          });
        })
        .catch(function () {});
    }

    function abrirPainel() {
      painel.hidden = false;
      botao.setAttribute("aria-expanded", "true");
      carregarHistorico();
      ajustarAlturaPainel();
      input.focus();
    }

    function fecharPainel() {
      painel.hidden = true;
      botao.setAttribute("aria-expanded", "false");
      painel.style.height = "";
    }

    botao.addEventListener("click", function () {
      if (painel.hidden) {
        abrirPainel();
      } else {
        fecharPainel();
      }
    });

    if (fechar) {
      fechar.addEventListener("click", fecharPainel);
    }

    // Chip de sugestão manda a mensagem direto (sem exigir mais um toque em
    // "Enviar" depois de preencher o campo).
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        enviarMensagem(chip.textContent.trim());
      });
    });

    function adicionarMensagem(texto, classes) {
      const bolha = document.createElement("div");
      bolha.className = "assistente-msg " + classes;
      bolha.textContent = texto;
      historico.appendChild(bolha);
      historico.scrollTop = historico.scrollHeight;
      return bolha;
    }

    function confirmarCartao(caixa, botaoConfirmar, aviso) {
      const token = caixa.dataset.token || "";
      botaoConfirmar.disabled = true;
      botaoConfirmar.textContent = "Confirmando...";
      aviso.hidden = true;

      chamarApi("/assistente/confirmar", { token: token })
        .then(function (dados) {
          if (dados.ok) {
            caixa.classList.add("confirmado");
            botaoConfirmar.textContent = "Confirmado";
            adicionarMensagem("Pronto, confirmado! Atualizando a página...", "assistente");
            setTimeout(function () {
              location.reload();
            }, 800);
          } else {
            botaoConfirmar.disabled = false;
            botaoConfirmar.textContent = "Confirmar";
            aviso.textContent = dados.motivo || dados.mensagem || "Não foi possível confirmar essa proposta.";
            aviso.hidden = false;
          }
        })
        .catch(function () {
          botaoConfirmar.disabled = false;
          botaoConfirmar.textContent = "Confirmar";
          aviso.textContent = "Não consegui falar com o assistente agora.";
          aviso.hidden = false;
        });
    }

    function adicionarCartao(cartao) {
      const caixa = document.createElement("div");
      caixa.className = "assistente-cartao";
      caixa.dataset.token = cartao.token || "";

      const resumo = document.createElement("div");
      resumo.className = "resumo";
      resumo.textContent = cartao.resumo || "";
      caixa.appendChild(resumo);

      const aviso = document.createElement("div");
      aviso.className = "aviso-cartao";
      aviso.hidden = true;
      caixa.appendChild(aviso);

      const botaoConfirmar = document.createElement("button");
      botaoConfirmar.type = "button";
      botaoConfirmar.className = "btn btn-sm";
      botaoConfirmar.textContent = "Confirmar";
      botaoConfirmar.addEventListener("click", function () {
        confirmarCartao(caixa, botaoConfirmar, aviso);
      });
      caixa.appendChild(botaoConfirmar);

      historico.appendChild(caixa);
      historico.scrollTop = historico.scrollHeight;
    }

    function definirCarregando(carregando) {
      enviar.disabled = carregando;
      input.disabled = carregando;
    }

    function enviarMensagem(texto) {
      texto = (texto || "").trim();
      if (!texto) {
        return;
      }

      adicionarMensagem(texto, "usuario");
      input.value = "";
      definirCarregando(true);
      const indicador = adicionarMensagem("digitando...", "assistente digitando");

      chamarApi("/assistente/mensagem", { mensagem: texto })
        .then(function (dados) {
          indicador.remove();
          if (dados.resposta) {
            adicionarMensagem(dados.resposta, "assistente");
          } else {
            adicionarMensagem(dados.mensagem || "Não consegui entender essa mensagem.", "assistente erro");
          }
          (dados.cartoes || []).forEach(adicionarCartao);
        })
        .catch(function () {
          indicador.remove();
          adicionarMensagem("Não consegui falar com o assistente agora.", "assistente erro");
        })
        .finally(function () {
          definirCarregando(false);
          input.focus();
        });
    }

    form.addEventListener("submit", function (evento) {
      evento.preventDefault();
      enviarMensagem(input.value);
    });
  });
})();
