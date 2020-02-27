$(document).ready(function() {
    var userTable;
    var tradeTable;

    init();

    function init() {
        userTable = $('#userTable').DataTable({
            "searching":false,
            "paging":   false,
            "ordering": false,
            "info":     false,
            "columnDefs": [
                {
                    targets: 0,
                    className: 'dt-center'
                },
                {
                    targets: 1,
                    className: 'dt-center'
                },
            ]
        });

        tradeTable = $('#tradeTable').DataTable({
            "searching":false,
            "paging":   false,
            "ordering": false,
            "info":     false,
            "columnDefs": [
                {
                    targets: 0,
                    className: 'dt-center'
                },
                {
                    targets: 1,
                    className: 'dt-center'
                },
                {
                    targets: 2,
                    className: 'dt-center'
                },
                {
                    targets: 3,
                    className: 'dt-center'
                },
            ]
        });
    }

    $("#enterButton").click(function() {
        settlementPrice = $("#settlementPriceInput").val();

        if(parseFloat(settlementPrice) <= 0) {
            alert("Your settlement price has to be positive.");
            return;
        }

        $.get("../api/settle?price=" + settlementPrice, settle)
        .fail(function(data) {
            if(data['responseJSON'] && data['responseJSON']['error']) {
                alert(data['responseJSON']['error']); 
            } else {
                alert(data['status'] + ": " + data['statusText']);  
            }
        });
    });

    function settle(data) {
        var tableData = [];
        var users = data["by_user"]

        for (var id in users) {
            var user = users[id];
            tableData.push([user["user"], user["pnl"]])
        }

        userTable.clear();
        userTable.rows.add(tableData);
        userTable.draw();

        var trades = data["by_trade"]
        tableData = []
        for (var id in trades) {
            var trade = trades[id];

            tableData.push([trade["buyer"], trade["price"], trade["seller"], trade["pnl_buyer"]])
        }

        tradeTable.clear();
        tradeTable.rows.add(tableData);
        tradeTable.draw();
    }

    function drawUserTable(data) {
        var levels = state["book"]["levels"];
        var tableData = [];

        levels.forEach(function(level) {
            var bids = level["bids"];
            var asks = level["asks"];
            var bidsText = "";
            var asksText = asks.length + " :";
            var priceText = level["price"];

            bids.reverse().forEach(function(bid) {
                bidsText = bidsText + bid["user"] + " ";
            });

            bidsText = bidsText + ": " + bids.length;

            asks.forEach(function(ask) {
                asksText = asksText + " " + ask["user"];
            });

            tableData.push([bidsText, priceText, asksText]);
        });

        orderBookTable.clear();
        orderBookTable.rows.add(tableData);
        orderBookTable.draw();
    }
});

