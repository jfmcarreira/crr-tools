(async function () {
    const panel = document.getElementById('push-notifications');
    const button = document.getElementById('enable-push');
    const status = document.getElementById('push-status');
    if (!window.isSecureContext || !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        status.textContent = 'Este navegador não suporta notificações. Usa HTTPS e, no iPhone, abre a app pelo ecrã principal.';
        return;
    }
    if (!panel.dataset.key) {
        status.textContent = 'As notificações ainda não foram configuradas pelo administrador.';
        return;
    }
    let registration;
    let subscription;
    async function save(method, value) {
        const response = await fetch(panel.dataset.endpoint, {
            method, credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': panel.dataset.csrf},
            body: JSON.stringify(value)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(typeof error.detail === 'string' ? error.detail : 'Não foi possível guardar as notificações. Tenta novamente.');
        }
    }
    function update() {
        button.textContent = subscription ? 'Desativar notificações' : 'Ativar notificações';
        button.disabled = Notification.permission === 'denied' && !subscription;
        status.textContent = subscription ? 'Notificações ativadas neste dispositivo.' :
            Notification.permission === 'denied' ? 'Notificações bloqueadas. Permite-as nas definições do navegador.' : 'Ativa para receber avisos neste dispositivo.';
    }
    try {
        registration = await navigator.serviceWorker.register(panel.dataset.worker, {scope: panel.dataset.scope});
        // Wait for this app's root worker, not an old /static/ registration.
        if (!registration.active) {
            await new Promise((resolve, reject) => {
                const worker = registration.installing || registration.waiting;
                if (!worker) return reject(new Error('Não foi possível preparar as notificações.'));
                worker.addEventListener('statechange', () => {
                    if (worker.state === 'activated') resolve();
                    if (worker.state === 'redundant') reject(new Error('Não foi possível preparar as notificações.'));
                });
                if (worker.state === 'activated') resolve();
            });
        }
        subscription = await registration.pushManager.getSubscription();
        // Reconcile the browser with the server (e.g. after restoring a backup).
        if (subscription) await save('POST', subscription.toJSON());
        update();
    } catch (error) {
        status.textContent = error.message;
        // An existing subscription may belong to a previous signed-in account.
        // Still allow removing it locally before subscribing to this account.
        if (!subscription) return;
        button.textContent = 'Desativar notificações';
        button.disabled = false;
    }
    button.addEventListener('click', async () => {
        button.disabled = true;
        try {
            if (subscription) {
                await save('DELETE', {endpoint: subscription.endpoint});
                await subscription.unsubscribe();
                subscription = null;
            } else {
                // Permission must be requested directly from the user's click (Safari).
                const permission = await Notification.requestPermission();
                if (permission !== 'granted') { update(); return; }
                const base64 = panel.dataset.key.replace(/-/g, '+').replace(/_/g, '/');
                const key = Uint8Array.from(atob(base64 + '='.repeat((4 - base64.length % 4) % 4)), c => c.charCodeAt(0));
                const created = await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: key});
                try { await save('POST', created.toJSON()); }
                catch (error) { await created.unsubscribe(); throw error; }
                subscription = created;
            }
            update();
        } catch (error) {
            status.textContent = error.message || 'Não foi possível ativar as notificações. Tenta novamente.';
        } finally {
            button.disabled = Notification.permission === 'denied' && !subscription;
        }
    });
})();
