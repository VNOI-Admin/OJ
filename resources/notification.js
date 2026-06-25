$(function () {
    var cfg = window.notificationConfig;
    if (!cfg) return;

    var $nav = $('#notification-nav');
    var $badge = $nav.find('.notification-badge');
    var $items = $nav.find('.notification-items');
    var $empty = $nav.find('.notification-empty');
    var currentStatus = 'all';

    function setBadge(count) {
        count = parseInt(count, 10) || 0;
        $badge.text(count);
        $badge.toggleClass('hidden', count === 0);
    }

    function renderItem(n) {
        var $item = $('<a>').addClass('notification-item').attr('href', n.url || '#')
            .attr('data-id', n.id).toggleClass('unread', !n.read);
        $('<div>').addClass('notification-item-title').text(n.title).appendTo($item);
        if (n.body) {
            $('<div>').addClass('notification-item-body').text(n.body).appendTo($item);
        }
        if (n.time && window.moment) {
            $('<div>').addClass('notification-item-time').text(moment(n.time).fromNow()).appendTo($item);
        }
        $item.on('click', function () {
            if (!n.read) markRead(n.id, true);
        });
        return $item;
    }

    function loadPanel() {
        $.get(cfg.ajaxUrl, {status: currentStatus}, function (data) {
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
        });
    }

    function markRead(id, read) {
        $.post(cfg.markReadUrl, {id: id, read: read ? '1' : '0'}, function (data) {
            setBadge(data.unread_count);
            var $item = $items.find('.notification-item[data-id="' + id + '"]');
            $item.toggleClass('unread', !read);
            if (read && currentStatus === 'unread') $item.remove();
        });
    }

    function markAllRead() {
        $.post(cfg.markReadUrl, {all: '1'}, function (data) {
            setBadge(data.unread_count);
            $items.find('.notification-item').removeClass('unread');
            if (currentStatus === 'unread') loadPanel();
        });
    }

    $nav.children('li').on('mouseenter', loadPanel);

    $nav.find('.notification-tab').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var $tab = $(this);
        if ($tab.hasClass('active')) return;
        $nav.find('.notification-tab').removeClass('active');
        $tab.addClass('active');
        currentStatus = $tab.data('status');
        loadPanel();
    });

    $nav.find('.notification-mark-all').on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        markAllRead();
    });

    $nav.find('.notification-panel-header').on('click', function (e) {
        e.stopPropagation();
    });
});
