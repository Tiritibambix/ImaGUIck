$( document ).ready(function() {
});

function skinSelector() {
	$("link[href*='user_skins']").remove();
	var thisSkin = $("#SkinSelector option:selected").val();
	var thisSkinCheckbox = $("div#SkinSelector input");
	var thisSkinSummary = $("div#summary div#Filter_Menu #SkinSelector option:selected").val();
	if(typeof thisSkinSummary !='undefined') {
		//slices
		halfDisplay(thisSkinSummary);
                if(thisSkinSummary !='basic_summary' && thisSkinSummary !='complete' && thisSkinSummary !='high_level' && thisSkinSummary !='mapping_friendly' 
			&& thisSkinSummary !='conceptual' && thisSkinSummary !='operational' && thisSkinSummary !='mappingfriendly' && thisSkinSummary !='custom') {
                        return;
                }
                $("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkinSummary + '.css" type="text/css" />');
                writeCookie("filter", thisSkinSummary, 365);
	} else if(thisSkinCheckbox.length !=0) {
		if(thisSkinCheckbox[0].checked){
			thisSkin = "true";
			$("head").append('<link rel="stylesheet" href="/css/user_skins/show_details.css" type="text/css" />');
		} else { 
			thisSkin = "false";
		}
                writeCookie("checkboxfilter", thisSkin, 365);
	} else if(typeof thisSkin !='undefined'){
		halfDisplay(thisSkin);
                if(thisSkin !='basic_summary' && thisSkin !='complete' && thisSkin !='high_level' && thisSkin !='mapping_friendly' &&
                   thisSkin !='show_details' && thisSkin !='conceptual' && thisSkin !='operational' && thisSkin !='mappingfriendly' && thisSkin != 'custom') {
                        return;
                }
                $("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />');
                writeCookie("filter", thisSkin, 365);
	} else {
		//Non Weakness/Slice/View
	}
}

function toggleNames(divid) {
	$(divid).toggleClass("hideIt");
}

function halfDisplay(stylesheet) {
	var hl_array = new Array('Time_of_Introduction', 'Alternate_Terms');
	var acq_array = new Array('Likelihood_of_Exploit', 'Detection_Methods', 'Background_Details');
	var devmgr_array = new Array('Alternate_Terms',	'Modes_of_Introduction', 'Background_Details', 'Weakness_Ordinalities');
	var deved_array = new Array('Observed_Examples', 'Modes_of_Introduction', 'Other_Notes');
	var vulnres_array = new Array('Applicable_Platforms', 'Detection_Methods', 'Potential_Mitigations', 'Related_Attack_Patterns', 'Taxonomy_Mappings', 'Modes_of_Introduction', 'White_Box_Definitions', 'Other_Notes');
	var mapping_array = new Array('Terminology_Notes', 'Related_Attack_Patterns', 'Relationship_Notes', 'Theoretical_Notes');

	if (stylesheet=='acquisition') {
		for(var i=0; i<acq_array.length; i++) {
			$("div[id*='_" + acq_array[i] + "']").each(function(){
			var thisId = $(this).attr('id');
				toggleblocksOC(thisId.substring(3))
			});
		}	
	}
	else if (stylesheet=='dev_manager') {
		for(var i=0; i<devmgr_array.length; i++) {
			$("div[id*='_" + devmgr_array[i] + "']").each(function(){
			var thisId = $(this).attr('id');
				toggleblocksOC(thisId.substring(3))
			});
		}	
	}
	else if (stylesheet=='dev_ed') {
		for(var i=0; i<deved_array.length; i++) {
			$("div[id*='_" + deved_array[i] + "']").each(function(){
			var thisId = $(this).attr('id');
				toggleblocksOC(thisId.substring(3))
			});
		}	
	}
	else if (stylesheet=='vuln_research') {
		for(var i=0; i<vulnres_array.length; i++) {
			$("div[id*='_" + vulnres_array[i] + "']").each(function(){
			var thisId = $(this).attr('id');
				toggleblocksOC(thisId.substring(3))
			});
		}	
	}
	else if (stylesheet=='mapping_friendly') {
		for(var i=0; i<mapping_array.length; i++) {
			$("div[id*='_" + mapping_array[i] + "']").each(function(){
			var thisId = $(this).attr('id');
				toggleblocksOC(thisId.substring(3))
			});
		}	
	}

}
function buttonSkinSelector(stylesheet) {
	$("link[href*='user_skins']").remove();
        var thisSkin = stylesheet;
        if(typeof thisSkin !='undefined') {       
		halfDisplay(thisSkin);
                if(thisSkin !='basic_summary' && thisSkin !='complete' && thisSkin !='high_level' && thisSkin !='mapping_friendly' &&
                   thisSkin !='show_details' && thisSkin !='conceptual' && thisSkin !='operational' && thisSkin !='mappingfriendly' && thisSkin !='custom') {
                        return;
                }
                $("head").append('<link rel="stylesheet" href="/css/user_skins/' + thisSkin + '.css" type="text/css" />');
                writeCookie("filter", thisSkin, 365);
        } else {
                //Non Weakness/Slice/View
        }
}

