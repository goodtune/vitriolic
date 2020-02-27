$(document).ready(function() {
    var orderBookTable;
    var tradesChartData = [];

    var es = new ReconnectingEventSource('../events/');

    es.addEventListener('state', function (e) {
        var data = JSON.parse(e.data);
        console.log(data);
        drawTradesChart(data);
        drawOrderBook(data);
        drawTradesList(data);
    }, false);

    es.addEventListener('stream-reset', function (e) {
        // ... client fell behind, reinitialize ...
    }, false);

    orderBookTable = $('#orderBookTable').DataTable({
        "searching":false,
        "paging":   false,
        "ordering": false,
        "info":     false,
        "columnDefs": [
            {
                className: 'text-right col-5',
                targets: 0
            },
            {
                className: 'text-center col-2',
                targets: 1
            },
            {
                className: 'text-left col-5',
                targets: 2
            }
        ]
    });

    $.getJSON("../state/", function(data) {
        console.log(data);
        drawTradesChart(data);
        drawOrderBook(data);
        drawTradesList(data);
    }).fail(function(data) {
        console.log(data);
    });

    function drawOrderBook(state) {
        var levels = state["book"]["levels"];
        var tableData = [];

        levels.forEach(function(level) {
            var bids = level["bids"];
            var asks = level["asks"];
            var bidsText = "";
            var asksText = "";
            var priceText = level["price"];

            bids.reverse().forEach(function(bid) {
                bidsText += `<span class="badge badge-info">${bid.user}</span>`;
            });

            if (bids.length) {
                var badgeClass = bids.length > 3 ? "badge-danger" : "badge-success";
                bidsText += `<span class="badge ${badgeClass}">${bids.length}</span>`;
            }

            if (asks.length) {
                var badgeClass = asks.length > 3 ? "badge-danger" : "badge-success";
                asksText += `<span class="badge ${badgeClass}">${asks.length}</span>`;
            }

            asks.forEach(function(ask) {
                asksText += `<span class="badge badge-warning">${ask.user}</span>`;
            });

            if (bids.length || asks.length) {
                tableData.push([bidsText, priceText, asksText]);
            }
        });

        if (levels.length == 0) {
            tableData.push(["", "No Orders Placed", ""])
        }

        orderBookTable.clear();
        orderBookTable.rows.add(tableData);
        orderBookTable.draw();
        $(orderBookTable.table().body()).children("tr").addClass("d-flex");
    }

    function drawTradesList(state) {
        var trades = state["trade_list"];
        var tradesText = "";
        trades.forEach(function(trade) {
            tradesText = (tradesText +
                trade["buyer"] + " bought @ " +
                trade["price"] + " from " +
                trade["seller"] + "\n");
        });

        $("#tradesTextArea").text(tradesText);
        $("#tradesTextArea").scrollTop($("#tradesTextArea")[0].scrollHeight);
    }

    function drawTradesChart(state) {
        var trades = state["trade_list"];
        var data = [];
        var labels = [];

        trades.forEach(function(trade) {
            data.push(trade["price"]);
            labels.push("");
        });

        if(data.length === tradesChartData.length && data.every(function(v,i) { return v === tradesChartData[i]})) return;
        tradesChartData = data;

        var ctx = document.getElementById("tradesChart").getContext('2d');
        var myChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Trade prices',
                    data: data,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.2)',
                    ],
                    borderColor: [
                        'rgba(255,99,132,1)',
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                scales: {
                    yAxes: [{
                        ticks: {
                            beginAtZero: false
                        }
                    }]
                }
            }
        });
    }
});

