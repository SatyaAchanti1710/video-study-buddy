"""A self-contained HTML flashcard viewer (flip, next/previous, shuffle)."""

from __future__ import annotations

import json

from .formatting import strip_markdown
from .schema import Flashcard

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: transparent; }
  body {
    font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1f2233;
  }
  .toolbar { display: flex; align-items: center; justify-content: space-between; margin: 2px 0 10px; }
  .counter { font-size: 13px; color: #5f6485; font-variant-numeric: tabular-nums; }
  button {
    font: inherit; font-size: 13px; border-radius: 999px; border: 1px solid #dcdfeb;
    background: #fff; color: #2c2f45; padding: 8px 14px; cursor: pointer;
    transition: border-color .15s ease, background .15s ease, transform .1s ease;
  }
  button:hover:not(:disabled) { border-color: #9aa0c3; }
  button:active:not(:disabled) { transform: translateY(1px); }
  button:disabled { opacity: .42; cursor: not-allowed; }
  button.shuffle { background: #5b5bd6; border-color: #5b5bd6; color: #fff; }
  button.shuffle:hover { background: #4b4bc4; border-color: #4b4bc4; }
  .progress { height: 4px; background: #ecedf5; border-radius: 999px; margin: 0 0 12px; overflow: hidden; }
  .bar { height: 100%; width: 0; background: #5b5bd6; border-radius: 999px; transition: width .25s ease; }
  .scene { height: 320px; perspective: 1600px; cursor: pointer; outline: none; border-radius: 18px; }
  .scene:focus-visible { box-shadow: 0 0 0 3px #c7c6ff; }
  .card { position: relative; width: 100%; height: 100%; transform-style: preserve-3d; transition: transform .55s cubic-bezier(.2,.7,.2,1); }
  .card.flipped { transform: rotateY(180deg); }
  .face {
    position: absolute; inset: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden;
    border-radius: 18px; border: 1px solid #e2e4f0; padding: 28px 26px 42px;
    background: #fff; box-shadow: 0 12px 30px rgba(32, 35, 70, .08);
    display: flex; flex-direction: column; justify-content: center; overflow-y: auto;
  }
  .face.back { transform: rotateY(180deg); background: linear-gradient(145deg, #f4f3ff 0%, #eef7ff 100%); }
  .badge {
    position: absolute; top: 16px; left: 20px; font-size: 10px; letter-spacing: .09em;
    text-transform: uppercase; color: #5b5bd6; background: #ecebff;
    border-radius: 999px; padding: 4px 9px; font-weight: 700;
  }
  .label {
    position: absolute; top: 18px; right: 22px; font-size: 10px; letter-spacing: .08em;
    text-transform: uppercase; color: #9297b5; font-weight: 600;
  }
  .text { white-space: pre-wrap; font-size: 19px; line-height: 1.5; font-weight: 600; }
  .back .text { font-size: 16px; line-height: 1.55; font-weight: 400; }
  .hint { position: absolute; bottom: 14px; left: 0; right: 0; text-align: center; font-size: 11px; color: #8a8fae; }
  .nav { display: flex; gap: 10px; margin-top: 14px; }
  .nav button { flex: 1; padding: 10px 14px; }
  .empty { padding: 40px; text-align: center; color: #5f6485; }
  @media (max-width: 520px) {
    .scene { height: 280px; }
    .text { font-size: 17px; }
    .back .text { font-size: 15px; }
    .face { padding: 26px 20px 40px; }
  }
  @media (prefers-color-scheme: dark) {
    .counter { color: #b9bdd8; }
    .progress { background: #2c2f45; }
    button { background: #1c1f2f; border-color: #3a3f5c; color: #e8e9f5; }
    button:hover:not(:disabled) { border-color: #6b7091; }
    button.shuffle { background: #6b6be8; border-color: #6b6be8; color: #fff; }
  }
  @media (prefers-reduced-motion: reduce) {
    .card { transition: none; }
  }
</style>
</head>
<body>
  <div class="toolbar">
    <span class="counter" id="counter">1 / 1</span>
    <button class="shuffle" id="shuffle" type="button">Shuffle</button>
  </div>
  <div class="progress"><div class="bar" id="bar"></div></div>
  <div class="scene" id="scene" tabindex="0" role="button" aria-label="Flashcard. Click or press Space to flip.">
    <div class="card" id="card">
      <div class="face front">
        <span class="badge" id="kindFront">Definition</span>
        <span class="label">Prompt</span>
        <div class="text" id="front"></div>
        <div class="hint">Click the card to flip</div>
      </div>
      <div class="face back">
        <span class="badge">Answer</span>
        <span class="label" id="kindBack">Definition</span>
        <div class="text" id="back"></div>
        <div class="hint">Click to flip back</div>
      </div>
    </div>
  </div>
  <div class="nav">
    <button id="prev" type="button">← Previous</button>
    <button id="next" type="button">Next →</button>
  </div>
<script>
  const CARDS = __CARDS__;
  const LABELS = { definition: "Definition", why_how: "Why / How", application: "Application" };
  let order = CARDS.map((_, i) => i);
  let pos = 0;

  const card = document.getElementById("card");
  const scene = document.getElementById("scene");
  const front = document.getElementById("front");
  const back = document.getElementById("back");
  const kindFront = document.getElementById("kindFront");
  const kindBack = document.getElementById("kindBack");
  const counter = document.getElementById("counter");
  const bar = document.getElementById("bar");
  const prev = document.getElementById("prev");
  const next = document.getElementById("next");
  const shuffle = document.getElementById("shuffle");

  function render() {
    if (!CARDS.length) return;
    const item = CARDS[order[pos]];
    const label = LABELS[item.kind] || "Card";
    front.textContent = item.front;
    back.textContent = item.back;
    kindFront.textContent = label;
    kindBack.textContent = label;
    counter.textContent = (pos + 1) + " / " + CARDS.length;
    bar.style.width = (((pos + 1) / CARDS.length) * 100) + "%";
    prev.disabled = pos === 0;
    next.disabled = pos === order.length - 1;
    card.classList.remove("flipped");
    scene.setAttribute("aria-pressed", "false");
  }

  function flip() {
    card.classList.toggle("flipped");
    scene.setAttribute("aria-pressed", card.classList.contains("flipped") ? "true" : "false");
  }

  function go(delta) {
    const target = pos + delta;
    if (target >= 0 && target < order.length) {
      pos = target;
      render();
    }
  }

  scene.addEventListener("click", flip);
  prev.addEventListener("click", () => go(-1));
  next.addEventListener("click", () => go(1));
  shuffle.addEventListener("click", () => {
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    pos = 0;
    render();
    scene.focus();
  });
  scene.addEventListener("keydown", (event) => {
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      flip();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      go(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      go(-1);
    }
  });

  render();
</script>
</body>
</html>"""


def flashcards_html(cards: list[Flashcard]) -> str:
    data = [
        {
            "front": strip_markdown(card.front),
            "back": strip_markdown(card.back),
            "kind": card.kind,
        }
        for card in cards
    ]
    payload = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    return _TEMPLATE.replace("__CARDS__", payload)
