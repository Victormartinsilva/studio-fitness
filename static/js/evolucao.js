/*
 * "Compartilhar evolução": usa a folha de compartilhamento nativa do
 * celular (Web Share API) com um resumo em texto do período — só variações,
 * sem nome nem medidas absolutas (montado no servidor, em evolucao.py).
 * Sem Web Share (desktop), copia o texto para a área de transferência.
 * Sem JS, o botão continua oculto (atributo `hidden` no template).
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    const botao = document.querySelector("[data-compartilhar]");
    const aviso = document.querySelector(".aviso-compartilhar");
    if (!botao) {
      return;
    }
    const texto = botao.dataset.texto || "";
    const podeCompartilhar = typeof navigator.share === "function";
    const podeCopiar = navigator.clipboard && typeof navigator.clipboard.writeText === "function";
    if (!texto || !(podeCompartilhar || podeCopiar)) {
      return;
    }
    botao.hidden = false;

    function avisar(mensagem) {
      if (!aviso) {
        return;
      }
      aviso.textContent = mensagem;
      aviso.hidden = false;
    }

    botao.addEventListener("click", function () {
      if (podeCompartilhar) {
        navigator.share({ title: "Minha evolução", text: texto }).catch(function () {
          /* usuário fechou a folha de compartilhamento: nada a fazer */
        });
        return;
      }
      navigator.clipboard.writeText(texto).then(
        function () {
          avisar("Resumo copiado — cole onde quiser compartilhar.");
        },
        function () {
          avisar("Não foi possível copiar o resumo.");
        }
      );
    });
  });
})();
