/*
 * RecruitSmart Help Assistant widget.
 *
 * Security-relevant design choices (read before editing):
 *   1. Every dynamic string coming from the server or the user is inserted
 *      with document.createTextNode / textContent, NEVER innerHTML+string
 *      concatenation. That means even if the FAQ endpoint ever returned
 *      attacker-influenced text, it could not execute as HTML/JS in the
 *      page -- this is what actually prevents stored/reflected XSS here,
 *      not just "trusting" the backend.
 *   2. The only exception is link_url, and that is only ever used as an
 *      <a href> (never eval'd), and only for values the server already
 *      resolved through Flask's url_for() against a fixed allow-list.
 *   3. Requests are debounced and the send button is disabled while a
 *      request is in flight, so a user mashing Enter can't flood the
 *      rate-limited endpoint (the server also enforces this independently
 *      via Flask-Limiter, so this is defense in depth, not the only check).
 *   4. The CSRF token is read from the <meta name="csrf-token"> tag Flask
 *      renders server-side and sent as the X-CSRFToken header, matching
 *      how Flask-WTF's CSRFProtect validates every other POST on this site.
 */
(function () {
    'use strict';

    var launcher, panel, body, form, input, sendBtn, chipsRow;
    var isOpen = false;
    var inFlight = false;
    var hasGreeted = false;

    function csrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function scrollToBottom() {
        body.scrollTop = body.scrollHeight;
    }

    function addUserMessage(text) {
        var row = document.createElement('div');
        row.className = 'rs-help-msg rs-help-msg-user';
        var bubble = document.createElement('div');
        bubble.className = 'rs-help-bubble';
        bubble.textContent = text; // textContent only -- never HTML
        row.appendChild(bubble);
        body.appendChild(row);
        scrollToBottom();
    }

    function botAvatar() {
        var icon = document.createElement('div');
        icon.className = 'rs-help-mini-icon';
        icon.innerHTML = '<i class="fas fa-robot" aria-hidden="true"></i>';
        return icon;
    }

    function addBotMessage(text, link) {
        var row = document.createElement('div');
        row.className = 'rs-help-msg rs-help-msg-bot';
        row.appendChild(botAvatar());
        var bubble = document.createElement('div');
        bubble.className = 'rs-help-bubble';
        bubble.appendChild(document.createTextNode(text));
        if (link && link.url && link.label) {
            bubble.appendChild(document.createElement('br'));
            var a = document.createElement('a');
            a.className = 'rs-help-link';
            a.href = link.url; // server-resolved via url_for(), fixed allow-list
            var icon = document.createElement('i');
            icon.className = 'fas fa-arrow-right';
            a.appendChild(icon);
            a.appendChild(document.createTextNode(' ' + link.label));
            bubble.appendChild(a);
        }
        row.appendChild(bubble);
        body.appendChild(row);
        scrollToBottom();
    }

    function showTyping() {
        var row = document.createElement('div');
        row.className = 'rs-help-msg rs-help-msg-bot';
        row.id = 'rs-help-typing-row';
        row.appendChild(botAvatar());
        var bubble = document.createElement('div');
        bubble.className = 'rs-help-bubble rs-help-typing';
        bubble.innerHTML = '<span></span><span></span><span></span>';
        row.appendChild(bubble);
        body.appendChild(row);
        scrollToBottom();
    }

    function hideTyping() {
        var row = document.getElementById('rs-help-typing-row');
        if (row) row.remove();
    }

    function setBusy(busy) {
        inFlight = busy;
        sendBtn.disabled = busy;
        input.disabled = busy;
    }

    function askServer(query) {
        setBusy(true);
        showTyping();
        fetch('/api/help/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken()
            },
            body: JSON.stringify({ query: query })
        })
            .then(function (res) {
                if (!res.ok) throw new Error('bad_status');
                return res.json();
            })
            .then(function (data) {
                hideTyping();
                var results = (data && data.results) || [];
                if (results.length === 0) {
                    addBotMessage(
                        "I couldn't find anything on that. Try asking about resumes, job matching, " +
                        "your account, security/2FA, or use the Contact page for a human."
                    );
                } else {
                    results.forEach(function (r) {
                        var link = r.link_url ? { url: r.link_url, label: r.link_label } : null;
                        addBotMessage(r.answer, link);
                    });
                }
            })
            .catch(function () {
                hideTyping();
                addBotMessage('Something went wrong reaching the help service. Please try again in a moment.');
            })
            .finally(function () {
                setBusy(false);
                input.focus();
            });
    }

    function handleSubmit(e) {
        e.preventDefault();
        if (inFlight) return;
        var text = input.value.trim().slice(0, 300);
        if (!text) return;
        addUserMessage(text);
        input.value = '';
        askServer(text);
    }

    function openPanel() {
        isOpen = true;
        panel.classList.add('rs-open');
        panel.setAttribute('aria-hidden', 'false');
        input.focus();
        if (!hasGreeted) {
            hasGreeted = true;
            setTimeout(function () {
                addBotMessage(
                    "Hi, I'm the RecruitSmart Assistant. Ask me anything, or tap a suggestion below."
                );
            }, 200);
        }
    }

    function closePanel() {
        isOpen = false;
        panel.classList.remove('rs-open');
        panel.setAttribute('aria-hidden', 'true');
    }

    function togglePanel() {
        if (isOpen) closePanel(); else openPanel();
    }

    document.addEventListener('DOMContentLoaded', function () {
        launcher = document.getElementById('rs-help-launcher');
        panel = document.getElementById('rs-help-panel');
        body = document.getElementById('rs-help-body');
        form = document.getElementById('rs-help-form');
        input = document.getElementById('rs-help-input');
        sendBtn = document.getElementById('rs-help-send');
        chipsRow = document.getElementById('rs-help-chips');

        if (!launcher || !panel) return; // widget markup not present on this page

        launcher.addEventListener('click', togglePanel);
        document.getElementById('rs-help-close').addEventListener('click', closePanel);
        form.addEventListener('submit', handleSubmit);

        chipsRow.querySelectorAll('.rs-help-chip').forEach(function (chip) {
            chip.addEventListener('click', function () {
                var q = chip.getAttribute('data-q');
                addUserMessage(q);
                askServer(q);
            });
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isOpen) closePanel();
        });
    });
})();
