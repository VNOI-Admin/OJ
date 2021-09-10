function WSEventDispatcher(websocket_path, polling_base, last_msg) {
    this.websocket_path = websocket_path;
    this.polling_path = polling_base;
    this.connected = false;
    this.last_msg = last_msg;
    this.events = {};
    this.channels = [];
    this.auto_reconnect = false;

    var receiver = this;
    var onwsclose_secret = 'wsclose_ZQ4hNB3vUc33q7Y7K1os';

    function Event() {
        this.callbacks = [];

        this.registerCallback = function (callback) {
            this.callbacks.push(callback);
        };

        this.fire = function (data) {
            this.callbacks.forEach((callback) => {
                callback(data);
            });
        }
    }

    function init_poll() {
        function long_poll() {
            receiver.polling_request = $.ajax({
                url: receiver.polling_path,
                data: {last: receiver.last_msg},
                success: function (data, status, jqXHR) {
                    receiver.dispatch(data.channel, data.message);
                    receiver.last_msg = data.id;
                    long_poll();
                },
                error: function (jqXHR, status, error) {
                    if (jqXHR.status == 504) {
                        long_poll();
                    } else if (jqXHR.statusText !== 'abort') {
                        console.log('Long poll failure: ' + status);
                        console.log(jqXHR);
                        setTimeout(long_poll, 2000);
                    }
                },
                dataType: 'json',
            });
        }
        long_poll();
    }

    function init_websocket() {
        receiver.websocket = new WebSocket(websocket_path);
        receiver.websocket.onopen = function () {
            receiver.websocket.send(JSON.stringify({
                command: 'start-msg',
                start: receiver.last_msg,
            }));
            receiver.websocket.readyForData = true;
        };
        receiver.websocket.onmessage = function (event) {
            var data = JSON.parse(event.data);
            receiver.dispatch(data.channel, data.message);
            receiver.last_msg = data.id;
        };
        receiver.websocket.onclose = function (event) {
            if (receiver.auto_reconnect) {
                console.log('Lost websocket connection! Attempt reconnecting in 1 second...');

                receiver.websocket = null;
                setTimeout(init_websocket, 1000);

                clearTimeout(filter_timeout);
                set_filters();
            } else if (event.code !== 1000) {
                receiver.dispatch(onwsclose_secret, event)
            }
        }
    }

    function init_connection() {
        if (window.WebSocket) {
            init_websocket();
        } else {
            init_poll();
        }
    }

    var filter_timeout = null;
    function set_filters() {
        if (window.WebSocket) {
            filter_timeout = setTimeout(function () {
                if (receiver.websocket &&
                    receiver.websocket.readyState === WebSocket.OPEN &&
                    receiver.websocket.readyForData === true) {
                    receiver.websocket.send(JSON.stringify({
                        command: 'set-filter',
                        filter: receiver.channels,
                    }));
                } else {
                    set_filters();
                }
            }, 200);
        } else {
            if (receiver.polling_request) {
                receiver.polling_request.abort();
                receiver.polling_request = null;
            }
            receiver.polling_path = polling_base + receiver.channels.join('|');
            init_poll();
        }
    }

    this.dispatch = function (event_name, data) {
        var event = this.events[event_name];
        if (event) {
            event.fire(data);
        }
    };

    this.on = function (event_name, callback) {
        if (!this.connected) {
            this.connected = true;
            init_connection();
        }
        if (!this.events[event_name]) {
            this.events[event_name] = new Event();
            this.channels.push(event_name);

            clearTimeout(filter_timeout);
            set_filters();
        }
        this.events[event_name].registerCallback(callback);
    };

    this.onwsclose = function (callback) {
        if (!this.events[onwsclose_secret]) {
            this.events[onwsclose_secret] = new Event();
        }
        this.events[onwsclose_secret].registerCallback(callback);
    };
}
