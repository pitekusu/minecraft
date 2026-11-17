(() => {
    "use strict";

    const app = window.bluemap;
    if (app?.settings?.version !== "5.29" || typeof app.initPlayerMarkerManager !== "function") {
        console.warn("BlueMap player polling requires the 5.29 web app.");
        return;
    }

    const installed = Symbol.for("tfg.bluemap.playerPolling");
    if (app[installed]) return;
    Object.defineProperty(app, installed, { value: true });

    const configuredManagers = new WeakSet();

    function keepPlayerPolling(manager) {
        if (!manager || manager.disposed || configuredManagers.has(manager)) return;
        configuredManagers.add(manager);

        const pause = manager.pauseAutoUpdates.bind(manager);
        const resume = manager.resumeAutoUpdates.bind(manager);
        const dispose = manager.dispose.bind(manager);
        // Leave the native polling timer in control even when SSE connects or retries.
        manager.pauseAutoUpdates = () => {};
        manager.resumeAutoUpdates = () => {};
        manager.dispose = () => {
            // A request finishing after a map switch must not schedule another timer.
            pause();
            dispose();
        };
        if (manager._paused) resume();
    }

    const initializePlayers = app.initPlayerMarkerManager;
    app.initPlayerMarkerManager = function (...args) {
        // BlueMap creates the new manager before returning its initial fetch promise.
        const initialFetch = initializePlayers.apply(this, args);
        keepPlayerPolling(this.playerMarkerManager);
        return initialFetch;
    };

    // BlueMap loads custom scripts after the first map and its SSE stream start.
    keepPlayerPolling(app.playerMarkerManager);
})();
