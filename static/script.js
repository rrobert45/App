function updateValue(variable, value) {
    $.ajax({
        type: 'POST',
        url: '/update_settings',
        data: JSON.stringify({ variable: variable, value: value }),
        contentType: 'application/json; charset=utf-8',
        dataType: 'json',
        success: function (response) {
            alert('Successfully updated ' + variable + ' to ' + value);
        }
    });
}