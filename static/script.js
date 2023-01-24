function updateValue(variable) {
    let newValue = prompt("Enter the new value for " + variable);
    if (newValue != null) {
        $.ajax({
            type: 'POST',
            url: '/update_settings',
            data: JSON.stringify({ variable: variable, value: newValue }),
            contentType: 'application/json; charset=utf-8',
            dataType: 'json',
            success: function (response) {
                alert('Successfully updated ' + variable + ' to ' + newValue);
            }
        });
    }
}