/**
 * VIGÍA Vision Systems — Controlador de la Vista de Inicio de Sesión (Sprint 01)
 *
 * Responsabilidades en Sprint 01:
 * - Validar campos obligatorios (usuario y contraseña) sin almacenar credenciales.
 * - Gestionar el estado visual de carga del botón de envío.
 * - Informar de manera accesible que la autenticación con el backend aún no está integrada.
 * - Mostrar el mensaje informativo oficial al accionar "¿Olvidaste la contraseña?".
 */

const MESSAGES = Object.freeze({
  MISSING_BOTH: 'Ingresa tu usuario y contraseña para continuar.',
  MISSING_USERNAME: 'Ingresa tu identificación de usuario.',
  MISSING_PASSWORD: 'Ingresa tu contraseña.',
  USERNAME_WHITESPACE: 'El identificador de usuario no debe contener espacios.',
  AUTH_NOT_INTEGRATED:
    'La autenticación todavía no está integrada con el servidor (Sprint 01). No se ha iniciado ninguna sesión.',
  PASSWORD_RECOVERY:
    'La recuperación de contraseñas debe solicitarse al administrador del sistema.',
  BUTTON_IDLE: 'Iniciar Sesión',
  BUTTON_LOADING: 'Verificando...'
});

/**
 * Actualiza el contenedor accesible de mensajes del formulario.
 * @param {HTMLElement} feedbackEl
 * @param {string} message
 * @param {'info' | 'warning' | 'error'} type
 */
function renderFeedback(feedbackEl, message, type = 'info') {
  if (!feedbackEl) return;

  feedbackEl.classList.remove(
    'login-feedback--info',
    'login-feedback--warning',
    'login-feedback--error'
  );
  feedbackEl.classList.add(`login-feedback--${type}`);
  feedbackEl.setAttribute('role', type === 'error' ? 'alert' : 'status');
  feedbackEl.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
  feedbackEl.textContent = message;
  feedbackEl.hidden = false;
}

/**
 * Oculta y limpia el área de mensajes.
 * @param {HTMLElement} feedbackEl
 */
function clearFeedback(feedbackEl) {
  if (!feedbackEl) return;
  feedbackEl.textContent = '';
  feedbackEl.hidden = true;
}

/**
 * Configura el estado de carga del formulario durante la verificación.
 * @param {HTMLButtonElement} submitBtn
 * @param {HTMLInputElement[]} inputs
 * @param {boolean} isLoading
 */
function setLoadingState(submitBtn, inputs, isLoading) {
  if (!submitBtn) return;

  submitBtn.disabled = isLoading;
  submitBtn.setAttribute('aria-busy', isLoading ? 'true' : 'false');
  submitBtn.textContent = isLoading ? MESSAGES.BUTTON_LOADING : MESSAGES.BUTTON_IDLE;

  inputs.forEach((input) => {
    if (input) {
      input.readOnly = isLoading;
    }
  });
}

/**
 * Inicializa los eventos y validaciones de la vista de Inicio de Sesión.
 * @param {Document | HTMLElement} root
 * @param {Object} [options]
 * @param {(authData: Object) => void} [options.onLoginSuccess]
 */
export function initLoginView(root = document, { onLoginSuccess } = {}) {
  const form = root.querySelector('#login-form');
  const usernameInput = root.querySelector('#username-input');
  const passwordInput = root.querySelector('#password-input');
  const submitBtn = root.querySelector('#login-submit-btn');
  const feedbackEl = root.querySelector('#login-feedback');
  const forgotLink = root.querySelector('#forgot-password-link');

  if (!form || !usernameInput || !passwordInput || !submitBtn || !feedbackEl) {
    return null;
  }

  const inputs = [usernameInput, passwordInput];

  inputs.forEach((input) => {
    input.addEventListener('input', () => {
      input.setAttribute('aria-invalid', 'false');
      if (!feedbackEl.hidden) {
        clearFeedback(feedbackEl);
      }
    });
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const rawUsername = usernameInput.value.trim();
    const rawPassword = passwordInput.value;

    usernameInput.setAttribute('aria-invalid', 'false');
    passwordInput.setAttribute('aria-invalid', 'false');

    if (!rawUsername && !rawPassword) {
      usernameInput.setAttribute('aria-invalid', 'true');
      passwordInput.setAttribute('aria-invalid', 'true');
      renderFeedback(feedbackEl, MESSAGES.MISSING_BOTH, 'error');
      usernameInput.focus();
      return;
    }

    if (!rawUsername) {
      usernameInput.setAttribute('aria-invalid', 'true');
      renderFeedback(feedbackEl, MESSAGES.MISSING_USERNAME, 'error');
      usernameInput.focus();
      return;
    }

    if (/\s/.test(rawUsername)) {
      usernameInput.setAttribute('aria-invalid', 'true');
      renderFeedback(feedbackEl, MESSAGES.USERNAME_WHITESPACE, 'error');
      usernameInput.focus();
      return;
    }

    if (!rawPassword) {
      passwordInput.setAttribute('aria-invalid', 'true');
      renderFeedback(feedbackEl, MESSAGES.MISSING_PASSWORD, 'error');
      passwordInput.focus();
      return;
    }

    // Estado visual de carga y solicitud real de autenticación al backend (ENR-02A)
    setLoadingState(submitBtn, inputs, true);

    (async () => {
      try {
        const resp = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            username: rawUsername,
            password: rawPassword
          })
        });

        const data = await resp.json().catch(() => ({}));
        // Por seguridad no se conserva la contraseña en memoria ni en el formulario
        passwordInput.value = '';
        setLoadingState(submitBtn, inputs, false);

        if (!resp.ok || !data.ok) {
          const errMsg = data.message || 'Credenciales inválidas o servicio no disponible.';
          renderFeedback(feedbackEl, errMsg, 'error');
          return;
        }

        // Sesión confirmada por el servidor
        if (typeof onLoginSuccess === 'function') {
          onLoginSuccess(data);
        } else {
          renderFeedback(
            feedbackEl,
            `Sesión iniciada como ${data.user?.nombre_completo || data.user?.username}.`,
            'info'
          );
        }
      } catch (netErr) {
        passwordInput.value = '';
        setLoadingState(submitBtn, inputs, false);
        renderFeedback(feedbackEl, 'Error de conexión con el servidor de autenticación.', 'error');
      }
    })();
  });

  if (forgotLink) {
    forgotLink.addEventListener('click', (event) => {
      event.preventDefault();
      usernameInput.setAttribute('aria-invalid', 'false');
      passwordInput.setAttribute('aria-invalid', 'false');
      renderFeedback(feedbackEl, MESSAGES.PASSWORD_RECOVERY, 'info');
    });
  }

  return {
    MESSAGES,
    renderFeedback,
    clearFeedback
  };
}

