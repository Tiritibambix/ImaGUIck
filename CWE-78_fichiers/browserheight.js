function browserheight(){
var myHeight = 0;
var agt=navigator.userAgent.toLowerCase();
if (agt.indexOf("safari") != -1) {
//Safari
myHeight = window.innerHeight;
myHeight = myHeight-265;
} else if (agt.indexOf("netscape") != -1) {
//Netscape
myHeight = window.innerHeight;
myHeight = myHeight-255;
} else if( typeof( window.innerWidth ) == 'number' ) {
//Non-IE & Firefox
myHeight = window.innerHeight;
myHeight = myHeight-255;
} else if( document.documentElement &&
  ( document.documentElement.clientWidth || document.documentElement.clientHeight ) ) {
//IE 6+ in 'standards compliant mode'
myHeight = document.documentElement.clientHeight;
myHeight = myHeight-255;
} else if( document.body && ( document.body.clientWidth || document.body.clientHeight ) ) {
//IE 4 compatible
myHeight = document.body.clientHeight;
myHeight = myHeight-255;
}
//document.getElementById('PageSpacer').style.height=myHeight+"px";

document.write( '<div style="height:' + myHeight + 'px; width:1px" id="PageSpacer" class="noprint"></div>');
}

function graphic() {
var myWidth = 0;
var agt=navigator.userAgent.toLowerCase();
if (agt.indexOf("safari") != -1) {
//Safari
myWidth = window.innerWidth;
myWidth = myWidth-400;
} else if (agt.indexOf("netscape") != -1) {
//Netscape
myWidth = window.innerWidth;
} else if( typeof( window.innerWidth ) == 'number' ) {
//Non-IE
myWidth = window.innerWidth;
} else if( document.documentElement &&
  ( document.documentElement.clientWidth || document.documentElement.clientHeight ) ) {
//IE 6+ in 'standards compliant mode'
myWidth = document.documentElement.clientWidth;
} else if( document.body && ( document.body.clientWidth || document.body.clientHeight ) ) {
//IE 4 compatible
myWidth = document.documentElement.clientWidth;
}

	if (myWidth > 1024) {
		document.getElementById('Graphic').style.background="url('/about/images/consensus.jpg')";
		document.getElementById('Graphic').style.height=389+"px";
		document.getElementById('Graphic').style.width=500+"px";
		document.getElementById('graphictable').style.width=530+"px";

	}
}
