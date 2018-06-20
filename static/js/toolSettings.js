
/*

	############################################
	zmienne i funkcje globalne narzędzi językowych

*/

var currLng = "";  //aktualnie wybrany język


$(document).ready(function(){


	/*
		###################################################
		pobieram napis z breadcrump i wklejam jako tab narzedzia w interfejsie

	*/
	var toolname = $('.breadcrumb-custom .breadcrumb-item:last-child a').html();
	$('.card#main-tool .tool-small-tab').html(toolname);


	/*
		###################################################
		Obsługa ustawień narzędzi
		###################################################
	*/

	// ################ obsługa języka #######

	//dotyczy tylko tych narzędzi w których opcja ustawiania języka istnieje czyli gdzie
	//jest znaleziony id=ust-lng.
	if ( $( "#ust-lng" ).length ) {

		var wj = localStorage.getItem("wybranyJezyk");

		//jezeli localStorage jest pusty
		if (wj === null) {
			//wtedy pierwszy z rozwijanej listy bedzie jako domyslny
			var pierwszyjezyk =  $('#ust-lng .dropdown-item:first-child').html();
			$('#curr-lng').html(pierwszyjezyk);
			currLng = $('#ust-lng .dropdown-item:first-child').attr('value');

			//jeżeli ktoś już ustawił język to ustawiam kontrolki zgodnie z wcześniejszym wyborem
		} else {
			$( "#ust-lng .dropdown-item" ).each(function( index ) {
				var j = $( this ).attr('value');
				if(j === wj){
					var zapisanyjezyk =  $(this).html();
					$('#curr-lng').html(zapisanyjezyk);
					currLng = $(this).attr('value');
				}
			});
		}

		//obsługa ręcznego wyboru języka i wpisywanie do globalnej zmiennej
		$('#ust-lng .dropdown-item').click(function(event){
			var whatclicked = $(event.currentTarget).attr('value');
			var contentClicked = $(event.currentTarget).html();
			$('#curr-lng').html(contentClicked);
			localStorage.setItem("wybranyJezyk", whatclicked);
		});

	}
});


