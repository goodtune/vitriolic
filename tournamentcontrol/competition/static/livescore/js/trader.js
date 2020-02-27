// setup event stream
$(document).ready(function() {
    var es = new ReconnectingEventSource('../events/');
    var ev = $('#events');
    var name = Cookies.get("participant_name");

    function updateQuotes(state) {
        var bid_label = $("#id_bid").parent("div").children("label");
        var ask_label = $("#id_ask").parent("div").children("label");

        if (Object.keys(state.orders.ask).indexOf(name) < 0) {
            ask_label.addClass("disabled");
        } else {
            ask_label.removeClass("disabled");
        }

        if (Object.keys(state.orders.bid).indexOf(name) < 0) {
            bid_label.addClass("disabled");
        } else {
            bid_label.removeClass("disabled");
        }
    }

    es.addEventListener('trade', function (e) {
        var data = JSON.parse(e.data);
        ev.append($(`<li class="list-group-item px-2 py-1 ${data.buyer == name ? 'list-group-item-info' : ''} ${data.seller == name ? 'list-group-item-warning' : ''}">${data.message}</li>`));
    }, false);

    es.addEventListener('state', function (e) {
        var data = JSON.parse(e.data);
        console.log(e);
        updateQuotes(data);
    }, false);

    es.addEventListener('stream-reset', function (e) {
        // ... client fell behind, reinitialize ...
    }, false);
});

// form submission
$(document).ready(function() {
    var f = $('form');
    f.on('submit', function(event) {
        event.preventDefault();

        var data = {};
        $.each(f.serializeArray(), function(i, field) {
            data[field.name] = field.value;
        });

        /*
         * Yes, I can check this client side, however we now have validation
         * in more than one place. Also, i18n - leave it server side.
         */
        // if (parseInt(data.bid) >= parseInt(data.ask)) {
        //     alert("Your sell price has to be more than your buy price.");
        //     return;
        // }

        console.log(`Quotes: {${data.bid}@${data.ask}}`);

        $.ajax({
            url: '.',
            type: "POST",
            data: data,
            success: function(response, status, xhr) {
                console.log("Quotes successfully inserted.", xhr.responseJSON);
            },
            error: function(xhr, errmsg, err) {
                $.each(xhr.responseJSON, function(key) {
                    $.each(xhr.responseJSON[key], function(index) {
                        console.log(xhr.responseJSON[key][index]);
                        alert(xhr.responseJSON[key][index]);
                    });
                });
            }
        });
    });
});
