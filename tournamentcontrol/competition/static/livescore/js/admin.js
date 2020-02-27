$(document).ready(function() {
    $('#upload').change(function(e) {
        var files = e.target.files;

        if (files.length == 0) {
            return;
        }

        var data = new FormData();
        data.append('upload', files[0]);

        $.ajax({
            url: '../api/upload',
            type: 'POST',
            data: data,
            cache: false,
            processData: false, // Don't process the files
            contentType: false, // Set content type to false as jQuery will tell the server its a query string request
            success: function()
            {
                console.log("uploaded");
                $("#choosePrompt").text("File uploaded");
            },
            error: function(data)
            {
                if(data['responseJSON'] && data['responseJSON']['error']) {
                    alert(data['responseJSON']['error']);
                } else {
                    alert(data['status'] + ": " + data['statusText']);
                }
            }
        });
    });

    $("#enterButton").click(function() {
        tickSize = $("#tickSizeInput").val();

        if(parseFloat(tickSize) <= 0) {
            alert("Your tick size has to be positive.");
            return;
        }

        $.get("../api/start?ticksize=" + tickSize,
            function(data, status) {
                console.log("started");
                window.location.href = "/media/dash.html";
            }
        ).fail(function(data) {
            if(data['responseJSON'] && data['responseJSON']['error']) {
                alert(data['responseJSON']['error']);
            } else {
                alert(data['status'] + ": " + data['statusText']);
            }
        });
    });


});
