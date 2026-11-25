/* Top-right rotate dock, selection chips, and Citizenship photo slot overlays. */

import { el } from "./dom.js";
import { clearIcon, rotateIcon } from "./icons.js";

export function createRotateDock(hooks) {
  const dock = el("div", { class: "rotate-dock" });
  const scope = el("button", {
    class: "rotate-scope",
    attrs: { type: "button", hidden: "hidden", "aria-label": "Clear selection" },
    on: { click: (event) => { event.stopPropagation(); hooks.onClear?.(); } },
  });
  const scopeText = el("span", { class: "rotate-scope-label" });
  scope.append(scopeText, clearIcon());

  const button = el("button", {
    class: "rotate-btn",
    attrs: { type: "button", "aria-label": "Rotate clockwise", title: "Rotate clockwise (R)" },
    on: {
      click: (event) => {
        event.stopPropagation();
        if (button.disabled) return;
        flickIcon(button);
        hooks.onRotate?.();
      },
    },
  });
  button.append(rotateIcon());
  dock.append(scope, button);
  return dock;
}

export function syncRotateDock(dock, state) {
  if (!dock) return;
  const button = dock.querySelector(".rotate-btn");
  const scope = dock.querySelector(".rotate-scope");
  const label = dock.querySelector(".rotate-scope-label");
  if (!button || !scope || !label) return;

  dock.hidden = !state.canRotate;
  button.disabled = Boolean(state.busy);

  const chip = scopeLabel(state);
  if (chip) {
    if (label.textContent !== chip) label.textContent = chip;
    if (scope.hidden) scope.hidden = false;
  } else if (!scope.hidden) {
    scope.hidden = true;
  }

  const tip = rotateTitle(state);
  button.setAttribute("aria-label", tip);
  button.setAttribute("title", tip + " (R)");
}

export function flickIcon(button) {
  if (!button || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const icon = button.querySelector("svg");
  if (!icon) return;
  icon.getAnimations().forEach((anim) => anim.cancel());
  icon.animate(
    [{ transform: "rotate(0deg)" }, { transform: "rotate(90deg)" }],
    { duration: 240, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
  );
}

export function paintPairSlots(layer, boxes, selectedSlot, onSelectSlot) {
  if (!layer) return;
  if (!Array.isArray(boxes) || boxes.length !== 2) {
    layer.replaceChildren();
    layer.hidden = true;
    return;
  }
  layer.hidden = false;
  const buttons = layer.querySelectorAll(".pair-slot");
  if (buttons.length !== 2) {
    layer.replaceChildren(
      slotButton(0, boxes[0], selectedSlot, onSelectSlot),
      slotButton(1, boxes[1], selectedSlot, onSelectSlot),
    );
    return;
  }
  for (let i = 0; i < 2; i += 1) placeSlot(buttons[i], boxes[i], selectedSlot === i);
}

function slotButton(index, box, selectedSlot, onSelectSlot) {
  const name = index === 0 ? "Front photo" : "Back photo";
  const btn = el("button", {
    class: "pair-slot",
    attrs: { type: "button", "aria-label": name, "data-slot": String(index) },
    on: {
      click: (event) => {
        event.stopPropagation();
        onSelectSlot?.(index);
      },
    },
  });
  placeSlot(btn, box, selectedSlot === index);
  return btn;
}

function placeSlot(btn, box, selected) {
  btn.style.left = (box.x * 100).toFixed(4) + "%";
  btn.style.top = (box.y * 100).toFixed(4) + "%";
  btn.style.width = (box.w * 100).toFixed(4) + "%";
  btn.style.height = (box.h * 100).toFixed(4) + "%";
  btn.classList.toggle("is-selected", Boolean(selected));
  btn.setAttribute("aria-pressed", selected ? "true" : "false");
}

function scopeLabel(state) {
  if (state.isPair) {
    if (state.selectedSlot === 0) return "Front";
    if (state.selectedSlot === 1) return "Back";
    return "";
  }
  if (state.selectedPage != null) return "Page " + state.selectedPage;
  return "";
}

function rotateTitle(state) {
  if (state.isPair) {
    if (state.selectedSlot === 0) return "Rotate front photo clockwise";
    if (state.selectedSlot === 1) return "Rotate back photo clockwise";
    return "Rotate sheet clockwise";
  }
  if (state.selectedPage != null) return "Rotate page " + state.selectedPage + " clockwise";
  if ((state.pageCount || 1) > 1) return "Rotate all pages clockwise";
  return "Rotate clockwise";
}
