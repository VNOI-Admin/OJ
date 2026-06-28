$(function () {
    var cfg = window.notificationConfig;
    if (!cfg) return;

    var CACHE_KEY = 'notif_cache_' + cfg.channel;
    var CACHE_TTL = 5 * 60 * 1000; // 5 minutes

    var $nav = $('#notification-nav');
    var $badge = $nav.find('.notification-badge');
    var $items = $nav.find('.notification-items');
    var $empty = $nav.find('.notification-empty');

    function setBadge(count) {
        count = parseInt(count, 10) || 0;
        $badge.text(count);
        $badge.toggleClass('hidden', count === 0);
    }

    function readCache() {
        try {
            var raw = localStorage.getItem(CACHE_KEY);
            if (!raw) return null;
            var cached = JSON.parse(raw);
            if (Date.now() - cached.ts > CACHE_TTL) return null;
            return cached;
        } catch (e) { return null; }
    }

    function writeCache(data) {
        try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({
                ts: Date.now(),
                unread_count: data.unread_count,
                notifications: data.notifications,
            }));
        } catch (e) {}
    }

    function clearCache() {
        try { localStorage.removeItem(CACHE_KEY); } catch (e) {}
    }

    function renderItem(n) {
        var $item = $('<a>').addClass('notification-item unread').attr('href', n.url || '#')
            .attr('data-id', n.id);
        $('<div>').addClass('notification-item-title').text(n.title).appendTo($item);
        if (n.body) {
            $('<div>').addClass('notification-item-body').text(n.body).appendTo($item);
        }
        if (n.time && window.moment) {
            $('<div>').addClass('notification-item-time').text(moment(n.time).fromNow()).appendTo($item);
        }
        $item.on('click', function (e) {
            if (!n.url) e.preventDefault();
            $item.remove();
            clearCache();
            $.post(cfg.markReadUrl, {id: n.id, read: '1'}, function (data) {
                setBadge(data.unread_count);
            });
        });
        return $item;
    }

    function renderPanel(data) {
        setBadge(data.unread_count);
        $items.empty();
        if (data.notifications.length === 0) {
            $empty.removeClass('hidden');
        } else {
            $empty.addClass('hidden');
            data.notifications.forEach(function (n) {
                $items.append(renderItem(n));
            });
        }
    }

    function loadPanel() {
        var cached = readCache();
        if (cached) {
            renderPanel(cached);
            return;
        }
        $.get(cfg.ajaxUrl, {status: 'unread'}, function (data) {
            writeCache(data);
            renderPanel(data);
        });
    }

    function markAllRead() {
        $.post(cfg.markReadUrl, {all: '1'}, function (data) {
            setBadge(data.unread_count);
            $items.empty();
            $empty.removeClass('hidden');
            clearCache();
        });
    }

    var $li = $nav.children('li');

    $nav.find('.notification-bell').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        if ($li.hasClass('open')) {
            $li.removeClass('open');
        } else {
            $li.addClass('open');
            loadPanel();
        }
    });

    $(document).on('click.notificationPanel', function () {
        $li.removeClass('open');
    });

    $nav.find('.notification-panel').on('click', function (e) {
        e.stopPropagation();
    });

    $nav.find('.notification-mark-all').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        markAllRead();
    });
});
