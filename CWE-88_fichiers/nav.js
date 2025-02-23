/* Graph collapse/expand */
var plus = '/images/plus.gif';
var minus = '/images/minus.gif';

function showHide(elementid){
	if (document.getElementById(elementid).className == 'closed'){
		document.getElementById(elementid).className = 'open';
		document.getElementById('arrow').innerHTML = 'less';
		document.getElementById('arrow').className = 'less';
	} else {
		document.getElementById(elementid).className = 'closed';
		document.getElementById('arrow').innerHTML = 'more';
		document.getElementById('arrow').className = 'more';
	}
} 

function toggleblocks (postid) {
	var whichpost = document.getElementById('block_' + postid);
	var whichimg = document.getElementById('img_' + postid);
	if (whichpost.className=="expandblock") {
		whichpost.className="collapseblock";
		whichimg.src=plus;
	}
	else {
		whichpost.className="expandblock";
		whichimg.src=minus;
	}
} 

function toggleAll (toggle) {
	var divs = $("div[id^='block_']");
	var imgs = document.getElementsByTagName("img");
	if (toggle=="expand") {
		for (x=0; x<divs.length; x++) {
			if ((divs[x].className=="collapseblock")) {
				divs[x].className="expandblock";
			}
		}
		for (x=0; x<imgs.length; x++) {
			if(imgs[x].getAttribute('src')==plus)
			{
			imgs[x].setAttribute('src',minus);
			imgs[x].setAttribute('alt','-')
			}
		}		
	}
	else {
		for (x=0; x<divs.length; x++) {
			if (divs[x].className=="expandblock") {
				divs[x].className="collapseblock";
			}
		}
		for (x=0; x<imgs.length; x++) {
		}
		for (x=0; x<imgs.length; x++) {
			if(imgs[x].getAttribute('src')==minus)
			{
				imgs[x].setAttribute('src',plus);
				imgs[x].setAttribute('alt','+')
			}
		}			
	}
} 


/* Arrow/Section opening/closing */

var less = '/images/head_less.gif';
var more = '/images/head_more.gif';

function showHideOC(elementid){
	if (document.getElementById(elementid).className == 'closed'){
		document.getElementById(elementid).className = 'open';
		document.getElementById('arrow').innerHTML = 'less';
		document.getElementById('arrow').className = 'less';

	} else {
		document.getElementById(elementid).className = 'closed';
		document.getElementById('arrow').innerHTML = 'more';
		document.getElementById('arrow').className = 'more';
	}
} 

function toggleblocksOC (postid) {
	var whichpost = document.getElementById('oc_' + postid);
	var whichimg = document.getElementById('ocimg_' + postid);
	if (whichpost.className=="expandblock") {
		whichpost.className="collapseblock";
		whichimg.src=less;		
	} else {
		whichpost.className="expandblock";
		whichimg.src=more;	
	}
} 

function toggleAllOC (toggle) {
	divs = document.getElementsByTagName("div");
	imgs = document.getElementsByTagName("img");
	if (toggle=="expand") {
		for (x=0; x<divs.length; x++) {
			if (divs[x].className=="collapseblock") {
				divs[x].className="expandblock";
			}
		}
		for (x=0; x<imgs.length; x++) {
			if(imgs[x].getAttribute('src')==less)
			{
			imgs[x].setAttribute('src',more);
			imgs[x].setAttribute('alt','-')
			}
		}		
	}
	else {
		for (x=0; x<divs.length; x++) {
			if (divs[x].className=="expandblock") {
				divs[x].className="collapseblock";
			}
		}
		for (x=0; x<imgs.length; x++) {
		}
		for (x=0; x<imgs.length; x++) {
			if(imgs[x].getAttribute('src')==more)
			{
				imgs[x].setAttribute('src',less);
				imgs[x].setAttribute('alt','+')
			}
		}		
	}
} 
