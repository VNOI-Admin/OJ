$(function () {
    var cfg = window.ticketNotify;
    if (!cfg) return;

    event_dispatcher.auto_reconnect = true;
    event_dispatcher.on(cfg.channel, function (data) {
        var prefix = data.type === 'new-ticket' ? cfg.newTicket : cfg.newReply;
        var ticketUrl = '/ticket/' + parseInt(data.id, 10);

        var $toast = $('<div>').css({
            position: 'fixed', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)', zIndex: 9999,
            background: '#3c3c3c', color: '#fff',
            padding: '28px 32px', borderRadius: '8px',
            width: 'max-content', maxWidth: '420px',
            boxShadow: '0 8px 32px rgba(0,0,0,.5)',
            fontFamily: 'inherit', fontSize: '16px', lineHeight: '1.6',
        });

        var $title = $('<div>').css({fontWeight: 'bold', fontSize: '18px', marginBottom: '8px'})
            .text(prefix + data.title);

        var $body = $('<div>').css({marginBottom: '20px', color: '#ccc'})
            .text(data.body.length > 200 ? data.body.slice(0, 200) + '…' : data.body);

        var btnBase = {
            display: 'inline-block', padding: '8px 20px', borderRadius: '4px',
            border: 'none', cursor: 'pointer', fontSize: '15px', marginRight: '10px',
        };
        var $access = $('<a>').attr({href: ticketUrl, target: '_blank'})
            .css($.extend({}, btnBase, {background: '#1a73e8', color: '#fff', textDecoration: 'none'}))
            .text(cfg.access)
            .on('click', function () { $toast.remove(); });

        var $close = $('<button>').css($.extend({}, btnBase, {background: '#555', color: '#fff'}))
            .text(cfg.close)
            .on('click', function () { $toast.remove(); });

        $toast.append($title, $body, $access, $close).appendTo('body');
    });
});
