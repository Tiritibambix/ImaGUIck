// Const. variable that we use to hold our settings for the custom filter
const custom_filter = [	
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



// Const. variable that holds all the checkboxes that should be changed when we select 'conceptual'
const conceptual_filter = [
        "Alternate_Terms",
	"Common_Consequences",
	"Memberships",
        "Relationships",
	"Taxonomy_Mappings",
	"Content_History"
]

// Const. variable that holds all the checkboxes that should be changed when we select 'operational'
const operational_filter = [
        "Applicable_Platforms",
	"Alternate_Terms",
	"Relationships",
	"Modes_Of_Introduction",
	"Potential_Mitigations",	
	"Demonstrative_Examples",
        "Observed_Examples", 	
	"Memberships",
	"Related_Attack_Patterns",
        "Content_History"
]

// Const. variable that holds all the checkboxes that should be changed when we select 'Mapping Friendly'
const mapping_friendly_filter = [
	"Alternate_Terms", 
	"Relationships",
	"Memberships",
        "Taxonomy_Mappings", 
	"Related_Attack_Patterns", 
	"Vulnerability_Mapping_Notes",
	"Notes", 
	"Content_History"
]

// Const. variable that holds all the checkboxes that should be changed when we select 'complete'
const complete_filter = [
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

function selectButtonSkin(stylesheet) {
        $("link[href*='user_skins']").remove();
        var thisSkin = stylesheet;
	if(typeof thisSkin !='undefined') {
                halfDisplay(thisSkin);
                if(thisSkin !='basic_summary' && thisSkin !='complete' && thisSkin !='high_level' && thisSkin !='mapping_friendly' &&
                   thisSkin !='show_details' && thisSkin !='conceptual' && thisSkin !='operational' && thisSkin !='mappingfriendly' && thisSkin !='custom') {
                        return;
                }
                if(thisSkin != 'custom') {
			var custom_more_message = document.getElementById("More_Message_Custom");
			if(custom_more_message != null) {
				custom_more_message.style.display = "none";
			}
		}
		$("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />');
                writeCookie("filter", thisSkin, 365);
		checkCustomStyle(); 
        } else {
                //Non Weakness/Slice/View
        }
}
 
// Const. variable that allows us to map the function call to the dictionary that will be used
const category_filter = {
	"conceptual": conceptual_filter,
	"operational": operational_filter,
	"mappingfriendly": mapping_friendly_filter,
	"complete": complete_filter
}


// Function we use to load up the custom filter modal when we click on the "Custom" filter
function openCustomFilterModal() {
	$("link[href*='user_skins']").remove();	
	$('<link/>', {
		title: "custom-filter",
		rel: "stylesheet",
		href: "/css/user_skins/custom.css",
  		type: 'text/css',
  		onload: function() {
  		}
	}).appendTo('head')
	var custom_cookie = [];
	if(readCookie("custom") == "") {
		var curr_filter = readCookie("filter");
		switch(curr_filter) {
  			case "conceptual":
    				custom_cookie = conceptual_filter;
    				break;
			case "operational":
				custom_cookie = operational_filter;
				break;
			case "mappingfriendly":
				custom_cookie = mapping_friendly_filter;
				break;
			case "complete":
				custom_cookie = complete_filter;
				break;
			default:
				custom_cookie = [];
		}
	} else {
		custom_cookie = readCookie("custom").split(",");
	}
	var modal = document.getElementById("customFilterModal");
        modal.style.display = "block";
        var leftBox = document.getElementById("customFilterLeftBox");
        var rightBox = document.getElementById("customFilterRightBox");
        var field_count = 0;
        custom_filter.forEach((value) => {
                var input_label = "<input type=\"checkbox\" name=\"chk\" id=\"" + value + "_chk\"><label for=\"" + value + "_chk\">" + value.replaceAll("_", " ") + "</label><br>"
                if(field_count < 12) {
                        leftBox.innerHTML += input_label
                } else {
                        rightBox.innerHTML += input_label
                }
                field_count += 1
        });
        custom_filter.forEach((value) => {
                if(custom_cookie.includes(value)) {
                        document.getElementById(value + "_chk").checked = true;
                }
        });	
	checkCustomStyle();
}


// Function we use when we exit out of the custom filter modal
function closeCustomFilterModal() {
    	// Get the modal
    	var modal = document.getElementById("customFilterModal");
	modal.style.display = "none";
	document.getElementById("customFilterLeftBox").innerHTML = "";
	document.getElementById("customFilterRightBox").innerHTML = "";
}


// Function we use when are selecting a category to have our filter be based off of
function selectCategory(category) {
    	var category_rules = category_filter[category]
	var ele = document.getElementsByName('chk');  
        if(category_rules !== undefined) {
		for(var i = 0; i < ele.length; i++) {  
        		if(ele[i].type=='checkbox' && category_rules.includes(ele[i].id.replace("_chk", ""))) {  
				ele[i].checked = true;
			} else {	
				ele[i].checked = false;
			}  
		} 
	} else {
		clearCustomFilter()
	}
}


// Function called when we press the clear button on the custom filter
function clearCustomFilter() {
	var ele = document.getElementsByName('chk');  
        for(var i = 0; i < ele.length; i++) {  
        	if(ele[i].type=='checkbox')  
                	ele[i].checked=false;  
	} 
}


// Function called for when we press the submit button on the custom filter
function submitCustomFilter() {	
	// All of the sub-classes of notes that we will want to have viewable if 'Notes' is selected
	const sub_notes = [
		".Applicable_Platform_Note",
		".Maintenance_Note",
		".Relationship_Note",
		".Research_Gap_Note",
		".Terminology_Note",
		".Theoretical_Note",
		".Other_Note"
	]
	// Variable that will be False unless we see that the 'Notes' section is set to True
	var notes_status = false;
	var missing_elements = [];
        var checked_fields = getCheckedFields();
	for(var i=0; i < document.styleSheets.length; i++) {
		if(document.styleSheets[i].title == "custom-filter") {
			var rules = document.styleSheets[i].cssRules;
			for (var j = 4; j < rules.length; j++) {
				var element = rules[j].selectorText.replace("#", "");
				if(checked_fields.includes(element) || (notes_status && sub_notes.includes(rules[j].selectorText))) {
					rules[j].style.display = "inline";
					if (element === "Notes")
						notes_status = true;
				}
				if(!checked_fields.includes(element) && document.getElementById(element) != null) {
					missing_elements.push(element);
				}	
			}
    		}
  	}
	// Clean off all the current styling that was used for when we initially loaded the page up
	custom_filter.forEach(function(element) {
		var found_element = document.getElementById(element);
		if(found_element != null && !checked_fields.includes(element)) {
			found_element.removeAttribute("style");
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
	writeCookie("custom", checked_fields.toString(), 365);
	writeCookie("filter", "custom", 365);
	closeCustomFilterModal();	
}

// Function called for when we want to reset the checkboxes to their original default values
function defaultCustomFilter() {
	var custom_cookie = readCookie("custom").split(",");
	custom_filter.forEach((value) => {
                if(custom_cookie.includes(value)) {
			document.getElementById(value + "_chk").checked = true;
                } else {
			document.getElementById(value + "_chk").checked = false;
		}
        });

}

// Function called for when the user hits the cancel button in the custom filter
function cancelCustomFilter() {
	buttonSkinSelector(readCookie("filter"));
	checkCustomStyle();
	closeCustomFilterModal();
}


// Returns a list of all the fields that are checked in the custom filter
function getCheckedFields() {
	var checked_fields = []
	var ele = document.getElementsByName('chk');  
        for(var i = 0; i < ele.length; i++) {  
        	if(ele[i].type=='checkbox' && ele[i].checked)  
                	checked_fields.push(ele[i].id.replace("_chk", ""));  
	}
	return checked_fields;
}

function checkCustomStyle() {
	if(readCookie("filter") == "custom") {
                var custom_cookie = readCookie("custom").split(",");
                custom_cookie.forEach(function(cookie) {
                        var element = document.getElementById(cookie)
                        if(element != null) {
                                element.style.display = "inline";
                        }
                });
        } else {
                custom_filter.forEach(function(element) {
                        var found_element = document.getElementById(element);
                        if(found_element != null) {
                                found_element.removeAttribute("style");
                        }
                });
        }
}
