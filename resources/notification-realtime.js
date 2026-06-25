$(function () {
    var cfg = window.notificationConfig;
    if (!cfg || !window.event_dispatcher) return;

    var CACHE_KEY = 'notif_cache_' + cfg.channel;
    var $badge = $('#notification-nav .notification-badge');

    function showToast(data) {
        var $toast = $('<div>').addClass('notification-toast');
        $('<div>').addClass('notification-toast-title').text(data.title).appendTo($toast);
        if (data.body) {
            var body = data.body.length > 200 ? data.body.slice(0, 200) + '…' : data.body;
            $('<div>').addClass('notification-toast-body').text(body).appendTo($toast);
        }
        var $actions = $('<div>').addClass('notification-toast-actions').appendTo($toast);
        if (data.url) {
            $('<a>').attr({href: data.url}).addClass('notification-toast-access').text(cfg.access)
                .on('click', function () { $toast.remove(); }).appendTo($actions);
        }
        $('<button>').addClass('notification-toast-close').text(cfg.close)
            .on('click', function () { $toast.remove(); }).appendTo($actions);
        $toast.appendTo('body');
    }

    event_dispatcher.auto_reconnect = true;
    event_dispatcher.on(cfg.channel, function (data) {
        try { localStorage.removeItem(CACHE_KEY); } catch (e) {}
        var count = (parseInt($badge.text(), 10) || 0) + 1;
        $badge.text(count).removeClass('hidden');
        if (data.popup) showToast(data);
    });
});
