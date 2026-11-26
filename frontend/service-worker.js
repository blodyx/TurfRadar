"use strict";

const APP_URL = "/turfradar/";
const ICON_URL = "/turfradar/icons/icon-192.png";

self.addEventListener("install", () => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
    let data = {
        title: "TurfRadar",
        body: "Ny händelse från radarn.",
        url: APP_URL,
    };

    if (event.data) {
        try {
            data = {
                ...data,
                ...event.data.json(),
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
                icon: ICON_URL,
                badge: ICON_URL,
                data: {
                    url: data.url,
                },
            }
        )
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl =
        event.notification.data?.url || APP_URL;

    event.waitUntil(
        (async () => {
            const windows = await clients.matchAll({
                type: "window",
                includeUncontrolled: true,
            });

            for (const client of windows) {
                if (
                    client.url.includes("/turfradar/") &&
                    "focus" in client
                ) {
                    await client.focus();

                    if ("navigate" in client) {
                        await client.navigate(targetUrl);
                    }

                    return;
                }
            }

            await clients.openWindow(targetUrl);
        })()
    );
});
