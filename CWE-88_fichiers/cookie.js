// Const. variable that we use to hold our settings for the custom filter
const complete_custom_filter = [	
	"Related_Weaknesses",
	"Weakness_Ordinalities",
	"Applicable_Platforms",
	"Background_Details",
	"Alternate_Terms",
	"Relationships",
	"Modes_Of_Introduction",
	"Exploitation_Factors",
	"Likelihood_Of_Exploit",
	"Common_Consequences",
	"Detection_Methods",
	"Potential_Mitigations",
	"Demonstrative_Examples",
	"Observed_Examples",
	"Functional_Areas",
	"Affected_Resources",
	"Memberships",
	"Taxonomy_Mappings",
	"Related_Attack_Patterns",
	"References",
	"Vulnerability_Mapping_Notes",
	"Notes",
	"Content_History"
]

// The version of the custom filter that we are currently on
const custom_version = 1;

function onloadCookie(){
	// If there is no cookie for the version of the custom filter
	if(readCookie("custom_version") != custom_version) {
		// Add the custom version cookie
		writeCookie("custom_version", custom_version, 365);
		// If the filter cookie is either complete or custom, reset it so we are on complete
		if(readCookie("filter") == "complete" || readCookie("filter") == "custom") {
			writeCookie("filter", "complete", 365);
			// Set the custom cookie to that of all the elements inside of the custom filter
			writeCookie("custom", complete_custom_filter, 365);
		}
	}
	var thisSkin = $("#Filter_Menu").length;
        var thisSkinCheckbox = $("div#SkinSelector input");
        var thisSkinSummary = $("div#summary div#Filter_Menu #SkinSelector option:selected").val();
	if(typeof thisSkinSummary !='undefined') {
		var filter = readCookie("filter");
		if (filter != "") {
			onloadSelector(filter);
		} else {
			writeCookie("filter", "complete", 365);
		}
        } else if(thisSkinCheckbox.length !=0) {
                var filter = readCookie("checkboxfilter");
		if (filter != "") {
                        onloadSelector(filter);
                } else {
                        writeCookie("checkboxfilter", "false", 365);
                }
        } else if(thisSkin != 0){
		var filter = readCookie("filter");
		if (filter != "") {
	                onloadSelector(filter);
                } else {
			writeCookie("filter", "complete", 365);
		}
        }	
	// Code we use to read in the code from the custom filter
	if(readCookie("filter") == "custom") {
		var custom_cookie = readCookie("custom").split(",");
		var missing_elements = [];
		custom_cookie.forEach(function(cookie) {
			var element = document.getElementById(cookie)
			if(element != null) {
				element.style.display = "inline";
			}
		});
		custom_filter.forEach(function(element) {
			if(!custom_cookie.includes(element) && document.getElementById(element) != null) {
				missing_elements.push(element);
			}
		});
		var custom_more_message = document.getElementById("More_Message_Custom");
		if(custom_more_message != null) {
			if(missing_elements.length > 0) {
				custom_more_message.style.display = "inline";
			} else {
				custom_more_message.style.display = "none";
			}
		}
	} else {
		custom_filter.forEach(function(element) {
			var found_element = document.getElementById(element);
			if(found_element != null) {
				found_element.removeAttribute("style");
			}	
		});	
	}
} 

function readCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function writeCookie(cname, cvalue, expdays) {
    var d = new Date();
    d.setTime(d.getTime() + (expdays*24*60*60*1000));
    var expires = "expires="+ d.toUTCString();
    document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}


function onloadSelector(thisSkin) {
	$("link[href*='user_skins']").remove();
        if(thisSkin !='complete' && thisSkin !='conceptual' && thisSkin !='operational' && thisSkin !='mappingfriendly' && thisSkin !='custom' && 
	   thisSkin !='false' && thisSkin !='true') {
		writeCookie("filter", "complete", 365);
		writeCookie("checkboxfilter", "false", 365);
		return;
        }
	var dropdownSelector = document.querySelectorAll("#SkinSelector");
        var checkboxSelector = document.querySelectorAll("div#SkinSelector input");
	var summarySelector = document.querySelectorAll("div#summary div#Filter_Menu #SkinSelector");

	if(summarySelector.length != 0){
                summarySelector[0].value = thisSkin;
		halfDisplay(thisSkin);
		$("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />');
	}
	else if(checkboxSelector.length != 0){
	    if(thisSkin == "true"){
		checkboxSelector[0].checked = true;
		$("head").append('<link rel="stylesheet" href="/css/user_skins/show_details.css" type="text/css" />');
	    }
        }
        else if(dropdownSelector.length != 0){ 
	    dropdownSelector[0].value = thisSkin;
	    halfDisplay(thisSkin);
	    $("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />'); 
        }
        else {
	    //nothing found to assign filter
	     halfDisplay(thisSkin);
            $("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />');

	}	
}
