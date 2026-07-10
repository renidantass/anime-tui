import { $ } from "./utils/dom.js";

let toastTimer;

export function toast(msg, isError = false) {
  const el = $("#toast");
  if (!el) return;
  clearTimeout(toastTimer);
  el.classList.remove("is-leaving", "is-loading");
  el.innerHTML = msg;
  el.classList.toggle("error", isError);
  el.hidden = false;
  toastTimer = setTimeout(() => {
    el.classList.add("is-leaving");
    toastTimer = setTimeout(() => {
      el.hidden = true;
      el.classList.remove("is-leaving", "is-loading");
    }, 220);
  }, 2800);
}

export function toastLoading(msg) {
  const el = $("#toast");
  if (!el) return;
  clearTimeout(toastTimer);
  el.classList.remove("is-leaving", "error");
  el.classList.add("is-loading");
  el.innerHTML = `<span class="toast-dot"></span>${msg}`;
  el.hidden = false;
}

export function dismissToast() {
  const el = $("#toast");
  if (!el) return;
  clearTimeout(toastTimer);
  el.classList.add("is-leaving");
  el.classList.remove("is-loading");
  toastTimer = setTimeout(() => {
    el.hidden = true;
    el.classList.remove("is-leaving", "is-loading");
  }, 220);
}
