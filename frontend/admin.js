const fmt = new Intl.NumberFormat("sv-SE");

function age(seconds) {

    if (seconds === null || seconds === undefined) {
        return "aldrig";
    }

    if (seconds < 60) {
        return `${seconds} s`;
    }

    if (seconds < 3600) {
        return `${Math.floor(seconds / 60)} min`;
    }

    if (seconds < 86400) {
        return `${Math.floor(seconds / 3600)} h`;
    }

    return `${Math.floor(seconds / 86400)} d`;
}


function setText(id, value) {
    document.getElementById(id).textContent = value;
}


async function loadStatus() {

    const status = document.getElementById("systemStatus");

    try {

        const response = await fetch("./api/admin/status", {
            credentials: "include",
            cache: "no-store"
        });

        if (response.status === 401) {
            window.location.href = "./";
            return;
        }

        if (response.status === 403) {
            status.className = "status error";
            status.innerHTML =
                '<span class="status-dot"></span><span>Ingen adminbehörighet</span>';
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        setText("dbSize", data.database.database_size);

        setText(
            "zoneCount",
            fmt.format(data.zones.zones)
        );

        setText(
            "ownedZones",
            fmt.format(data.zones.owned_zones)
        );

        setText(
            "userCount",
            fmt.format(data.users.length)
        );

        setText(
            "visiblePlayers",
            fmt.format(data.radar.visibleUniquePlayers)
        );

        setText(
            "fttCandidates",
            fmt.format(data.zones.ftt_candidates)
        );


        document.getElementById("workerState").innerHTML =
            data.systemState.map(item => `
                <div class="worker">
                    <div class="worker-key">
                        ${item.key}
                    </div>

                    <div class="worker-value">
                        ${item.value}
                        <span class="worker-age">
                            ${age(item.age_seconds)}
                        </span>
                    </div>
                </div>
            `).join("");


        document.getElementById("usersTable").innerHTML =
            data.users.map(user => `

                <tr>

                    <td>
                        <strong>${user.turf_name}</strong>
                        <div class="muted">
                            ${user.turf_user_id}
                        </div>
                    </td>

                    <td>
                        <span class="badge ${user.radar_enabled ? "on" : "off"}">
                            ${user.radar_enabled ? "På" : "Av"}
                        </span>
                    </td>

                    <td>
                        ${fmt.format(user.radius_m)} m
                    </td>

                    <td>
                        ${age(user.position_age_seconds)}
                    </td>

                    <td>
                        ${user.push_subscriptions}
                    </td>

                </tr>

            `).join("");


document.getElementById("tablesTable").innerHTML =
    data.tables
        .filter(table => [
            "zones",
            "users",
            "user_auth",
            "user_sessions",
            "auth_challenges",
            "auth_tokens",
            "push_subscriptions",
            "system_state",
            "user_medals",
            "user_taken_players",
            "user_taken_zones",
            "turfa_taken_players",
            "radar_player_state",
            "radar_ftt_state"
        ].includes(table.table_name))
        .map(table => `
            <tr>
                <td>${table.table_name}</td>
                <td>${fmt.format(table.estimated_rows)}</td>
                <td>${table.total_size}</td>
            </tr>
        `).join("");

        status.className = "status ok";

        status.innerHTML =
            '<span class="status-dot"></span><span>Online</span>';

        setText(
            "lastRefresh",
            `Uppdaterad ${new Date().toLocaleTimeString("sv-SE")}`
        );

    } catch (error) {

        console.error(error);

        status.className = "status error";

        status.innerHTML =
            '<span class="status-dot"></span><span>Fel</span>';
    }
}


loadStatus();

setInterval(loadStatus, 30000);
