self.addEventListener("install", () => {
    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", event => {
    let data = {
        title: "TurfRadar",
        body: "Ny händelse från radarn.",
        url: "/turfradar/"
    };

    if (event.data) {
        try {
            data = {
                ...data,
                ...event.data.json()
            };
        } catch {
            data.body = event.data.text();
        }
    }

    event.waitUntil(
        self.registration.showNotification(
            data.title,
            {
                body: data.body,
                icon: "/turfradar/icons/icon-192.png",
                badge: "/turfradar/icons/icon-192.png",
                data: {
                    url: data.url
                }
            }
        )
    );
});

self.addEventListener("notificationclick", event => {
    event.notification.close();

    const url =
        event.notification.data?.url ||
        "/turfradar/";

    event.waitUntil(
        clients.openWindow(url)
    );
});

