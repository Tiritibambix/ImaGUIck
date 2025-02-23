function styledPopupClose() {
  document.getElementById("styled_popup").style.display = "none";
}

function getDef(term) {
var term = 'CWE_Term[Term_Name=\'' + term + '\']';
  $.ajax({
	type: "GET",
	url: "/data/docs/glossary.xml",
	dataType: "xml",
	success: function(xml) {
		  $(xml).find(term).each(function() {
			if ($(this).attr("See_Also")) {
				var newterm = $(this).attr("See_Also");
				getDef(newterm);
			}
			else {
				$("#output").html('<div><b>' + $(this).attr("Term_Name") + '</b></div>');
				$("#output").append('<div style="padding-left:10px">' + $(this).find("Term_Definition").text() + "</div>");
			}
	  });
	  document.getElementById("styled_popup").style.display="block";
	}
  });
}
