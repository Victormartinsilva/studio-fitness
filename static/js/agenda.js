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
    // dela, descontando o `.topbar` fixo (senão o alvo fica escondido
    // atrás dele) e uma margem extra pra não colar no cabeçalho sticky da
    // coluna de equipamento.
    const topbar = document.querySelector(".topbar");
    const alturaTopbar = topbar ? topbar.getBoundingClientRect().height : 0;
    const margem = 16;

    const destino = pista.getBoundingClientRect().top + window.pageYOffset + alvoPx - alturaTopbar - margem;
    window.scrollTo(0, Math.max(destino, 0));
  });
})();
