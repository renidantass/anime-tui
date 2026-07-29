import { api } from "./api.js";

export async function requireAuth() {
  try {
    return await api.me();
  } catch (error) {
    if (error.status !== 401) throw error;
  }

  document.body.innerHTML = `<main class="auth-shell">
    <section class="auth-panel" aria-labelledby="auth-title">
      <div class="auth-brand">
        <span class="brand-mark" aria-hidden="true">ア</span>
        <span class="brand-text"><strong>anishelf</strong><small>multi-fonte</small></span>
      </div>
      <div class="auth-kicker"><span></span> acesso restrito</div>
      <h1 id="auth-title">Continue de onde parou.</h1>
      <p class="auth-lead" id="auth-message">Entre para acessar seu histórico, favoritos e progresso.</p>
      <form id="auth-form" class="auth-form">
        <label for="auth-email">E-mail</label>
        <input id="auth-email" name="email" type="email" required autocomplete="email" placeholder="voce@exemplo.com">
        <label for="auth-password">Senha</label>
        <input id="auth-password" name="password" type="password" minlength="8" required autocomplete="current-password" placeholder="Mínimo de 8 caracteres">
        <p class="auth-error" id="auth-error" role="alert" hidden></p>
        <button type="submit" class="btn btn-accent auth-submit">Entrar</button>
      </form>
      <div class="auth-switch"><span id="auth-switch-label">Ainda não tem uma conta?</span>
        <button type="button" class="auth-switch-btn" id="auth-register">Criar conta</button>
      </div>
      <div class="auth-status"><span></span> seus dados ficam separados por usuário</div>
    </section>
    <aside class="auth-aside" aria-hidden="true">
      <div class="auth-aside-grid"></div><div class="auth-orbit auth-orbit-one"></div><div class="auth-orbit auth-orbit-two"></div>
      <div class="auth-aside-copy"><span>ANIME / SHELF</span><strong>Seu universo,<br>seu ritmo.</strong><small>Histórico sincronizado. Favoritos sempre à mão.</small></div>
      <div class="auth-aside-code">SYS.AUTH // 01<br>SESSION READY</div>
    </aside>
  </main>`;
  const form = document.querySelector("#auth-form");
  const message = document.querySelector("#auth-message");
  const errorBox = document.querySelector("#auth-error");
  let register = false;
  document.querySelector("#auth-register").onclick = () => {
    register = !register;
    form.querySelector("button[type=submit]").textContent = register ? "Cadastrar" : "Entrar";
    form.querySelector("#auth-password").autocomplete = register ? "new-password" : "current-password";
    document.querySelector("#auth-title").textContent = register ? "Crie seu espaço." : "Continue de onde parou.";
    message.textContent = register ? "Uma conta para manter seu histórico e favoritos sincronizados." : "Entre para acessar seu histórico, favoritos e progresso.";
    document.querySelector("#auth-switch-label").textContent = register ? "Já tem uma conta?" : "Ainda não tem uma conta?";
    document.querySelector("#auth-register").textContent = register ? "Entrar" : "Criar conta";
  };
  return new Promise(() => {
    form.onsubmit = async (event) => {
      event.preventDefault();
      const body = Object.fromEntries(new FormData(form));
      try {
        const user = register ? await api.register(body) : await api.login(body);
        location.reload();
      } catch (error) {
        errorBox.textContent = error.message;
        errorBox.hidden = false;
      }
    };
  });
}

export function mountUserIndicator(user) {
  const email = String(user?.email || "");
  const emailEl = document.querySelector("#user-email");
  const avatarEl = document.querySelector("#user-avatar");
  if (emailEl) emailEl.textContent = email;
  if (avatarEl) avatarEl.textContent = (email[0] || "?").toUpperCase();
  document.querySelector("#user-logout")?.addEventListener("click", async () => {
    await api.logout();
    location.reload();
  });
}
