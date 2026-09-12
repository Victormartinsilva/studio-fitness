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
