<!-- This is an opera userjs for the creation of visual objects  -->
<!-- through oipfObjectFactory as specified in OIPF DAE 7.1.1.1. -->

/* Hide all helper functions under a single name, to avoid polluting the global
 * namespace */
var ooif_helper =
{

	OperaToOipfStandardMap: new Object(),
	UNICODE_PRIVATE_AREA_OFFSET_FOR_OIPF: 57856,

    getAppMgr: function(e) {
        if (typeof ooif_helper.appMgr == 'undefined')
            ooif_helper.appMgr = oipfObjectFactory.createApplicationManagerObject();

        return ooif_helper.appMgr;
    },

	createVisualObject: function(objectType) {
		if (oipfObjectFactory.isObjectSupported(objectType) == true) {
			element = document.createElement("object");
			element.setAttribute("type", objectType);
			return element;
		} else {
			throw {name: "TypeError"};
		}
	},

	fullscreen: function(video) {
		var style = video.style;
		var saved_state = {
			v: video,
			p: style.position,
			l: style.left,
			t: style.top,
			w: style.width,
			h: style.height
		};

		style.position = "fixed";
		style.left = "0px";
		style.top = "0px";
		style.width = "1280px";
		style.height = "720px";

		return saved_state;
	},

	restore: function(saved_state) {
		var style = saved_state.v.style;
		style.position = saved_state.p;
		style.left = saved_state.l;
		style.top = saved_state.t;
		style.width = saved_state.w;
		style.height = saved_state.h;
	},

	defineVirtualKey: function(keySymbol, keyValue)
	{
		window.KeyEvent[keySymbol] = keyValue;
		window.Event.prototype[keySymbol] = keyValue;
		window[keySymbol] = keyValue;
	},

	defineVirtualKeyWithOffset: function(keySymbol, standarizedKeyValue, operaValue)
	{
		ooif_helper.defineVirtualKey(keySymbol, standarizedKeyValue);

		var keyValueWithOffset = ooif_helper.UNICODE_PRIVATE_AREA_OFFSET_FOR_OIPF + operaValue;
		ooif_helper.OperaToOipfStandardMap[keyValueWithOffset] = standarizedKeyValue;
	},


	handleKey: function(e) {
		try {
			ooif_helper.getAppMgr().__key(e.event.type, e.event.keyCode);
		} catch (e)	{
			// we are unable to create DAE ApplicationManager so we can assume that
			// DAE applications are not suported by Opera (due to missing proper NJSE)
			// or
			// __key() is called inside non-DAE-application environment
			window.opera.removeEventListener('AfterEvent.keypress', ooif_helper.handleKey, false);
			window.opera.removeEventListener('AfterEvent.keydown', ooif_helper.handleKey, false);
			window.opera.removeEventListener('AfterEvent.keyup', ooif_helper.handleKey, false);
		}
	},

	translateVirtualKeyWithOffset: function(e)
	{
		if (e.event.keyCode < ooif_helper.UNICODE_PRIVATE_AREA_OFFSET_FOR_OIPF || !(e.event.keyCode in ooif_helper.OperaToOipfStandardMap))
		{
			return;
		}

		// we're creating copy of the original event, so it needs to be abandoned
		e.preventDefault();

		function createEventPartialClone(evt)
		{
			function isReadOnlyEventAttribute(attr)
			{
				readOnlyAttributes = ['type', 'target', 'currentTarget',
								   'eventPhase', 'bubbles', 'cancelable',
								   'timeStamp', 'srcElement', 'defaultPrevented', 'isTrusted'];
				return readOnlyAttributes.indexOf(attr) != -1;
			}

			var eventClone = document.createEvent('Events');

			eventClone.initEvent(evt.type, evt.bubbles, evt.cancelable);

			for (attr in evt)
			{
				// don't copy readonly attributes (causes exception),
				if (!isReadOnlyEventAttribute(attr))
				{
					eventClone[attr] = evt[attr];
				}
			}
			return eventClone;
		}

		function remapToOipfStandard(evt)
		{
			if (evt.keyCode in ooif_helper.OperaToOipfStandardMap)
			{
				evt.keyCode = ooif_helper.OperaToOipfStandardMap[evt.keyCode];
				evt.which = evt.keyCode;
			}
			return evt;
		}

		eventPartialClone = createEventPartialClone(e.event);
		translatedEvent = remapToOipfStandard(eventPartialClone);
		e.event.target.dispatchEvent(translatedEvent);
	},

    triggerApplicationLoadedEvent: function(e) {
		try {
			//check that it is the page loading, not just an image
			if(e.event.target instanceof Document)
				ooif_helper.getAppMgr().__triggerApplicationLoadedEvent();
		} catch (e)	{
			// we are unable to create DAE ApplicationManager so we can assume that
			// DAE applications are not suported by Opera (due to missing proper NJSE)
			// or
			// __triggerApplicationLoadedEvent() is called inside non-DAE-application environment
		}
    }
};

oipfObjectFactory.createVideoBroadcastObject = function() {
    return ooif_helper.createVisualObject("video/broadcast");
};

oipfObjectFactory.createVideoMpegObject = function() {
    return ooif_helper.createVisualObject("video/mpeg");
};


// OIPF 2.1 cross application event handling [4.4.7]
// begin {
window.opera.addEventListener('BeforeEvent.load', ooif_helper.triggerApplicationLoadedEvent, false);

window.opera.addEventListener('AfterEvent.keypress', ooif_helper.handleKey, false);
window.opera.addEventListener('AfterEvent.keydown', ooif_helper.handleKey, false);
window.opera.addEventListener('AfterEvent.keyup', ooif_helper.handleKey, false);
// } end [4.4.7]

<!-- This part adds support for key symbols as defined in Annex F of CEA-2014 -->
var KeyEvent = new Object();

ooif_helper.defineVirtualKey("VK_UNDEFINED",                      0);
ooif_helper.defineVirtualKey("VK_CANCEL",                         3);
ooif_helper.defineVirtualKey("VK_BACK_SPACE",                     8);
ooif_helper.defineVirtualKey("VK_TAB",                            9);
ooif_helper.defineVirtualKey("VK_CLEAR",                          12);
ooif_helper.defineVirtualKey("VK_ENTER",                          13);
ooif_helper.defineVirtualKey("VK_SHIFT",                          16);
ooif_helper.defineVirtualKey("VK_CONTROL",                        17);
ooif_helper.defineVirtualKey("VK_ALT",                            18);
ooif_helper.defineVirtualKey("VK_PAUSE",                          19);
ooif_helper.defineVirtualKey("VK_CAPS_LOCK",                      20);
ooif_helper.defineVirtualKey("VK_KANA",                           21);
ooif_helper.defineVirtualKey("VK_FINAL",                          24);
ooif_helper.defineVirtualKey("VK_KANJI",                          25);
ooif_helper.defineVirtualKey("VK_ESCAPE",                         27);
ooif_helper.defineVirtualKey("VK_CONVERT",                        28);
ooif_helper.defineVirtualKey("VK_NONCONVERT",                     29);
ooif_helper.defineVirtualKey("VK_ACCEPT",                         30);
ooif_helper.defineVirtualKey("VK_MODECHANGE",                     31);
ooif_helper.defineVirtualKey("VK_SPACE",                          32);
ooif_helper.defineVirtualKey("VK_PAGE_UP",                        33);
ooif_helper.defineVirtualKey("VK_PAGE_DOWN",                      34);
ooif_helper.defineVirtualKey("VK_END",                            35);
ooif_helper.defineVirtualKey("VK_HOME",                           36);
ooif_helper.defineVirtualKey("VK_LEFT",                           37);
ooif_helper.defineVirtualKey("VK_UP",                             38);
ooif_helper.defineVirtualKey("VK_RIGHT",                          39);
ooif_helper.defineVirtualKey("VK_DOWN",                           40);
ooif_helper.defineVirtualKey("VK_COMMA",                          44);
ooif_helper.defineVirtualKey("VK_PERIOD",                         46);
ooif_helper.defineVirtualKey("VK_SLASH",                          47);
ooif_helper.defineVirtualKey("VK_0",                              48);
ooif_helper.defineVirtualKey("VK_1",                              49);
ooif_helper.defineVirtualKey("VK_2",                              50);
ooif_helper.defineVirtualKey("VK_3",                              51);
ooif_helper.defineVirtualKey("VK_4",                              52);
ooif_helper.defineVirtualKey("VK_5",                              53);
ooif_helper.defineVirtualKey("VK_6",                              54);
ooif_helper.defineVirtualKey("VK_7",                              55);
ooif_helper.defineVirtualKey("VK_8",                              56);
ooif_helper.defineVirtualKey("VK_9",                              57);
ooif_helper.defineVirtualKey("VK_SEMICOLON",                      59);
ooif_helper.defineVirtualKey("VK_EQUALS",                         61);
ooif_helper.defineVirtualKey("VK_A",                              65);
ooif_helper.defineVirtualKey("VK_B",                              66);
ooif_helper.defineVirtualKey("VK_C",                              67);
ooif_helper.defineVirtualKey("VK_D",                              68);
ooif_helper.defineVirtualKey("VK_E",                              69);
ooif_helper.defineVirtualKey("VK_F",                              70);
ooif_helper.defineVirtualKey("VK_G",                              71);
ooif_helper.defineVirtualKey("VK_H",                              72);
ooif_helper.defineVirtualKey("VK_I",                              73);
ooif_helper.defineVirtualKey("VK_J",                              74);
ooif_helper.defineVirtualKey("VK_K",                              75);
ooif_helper.defineVirtualKey("VK_L",                              76);
ooif_helper.defineVirtualKey("VK_M",                              77);
ooif_helper.defineVirtualKey("VK_N",                              78);
ooif_helper.defineVirtualKey("VK_O",                              79);
ooif_helper.defineVirtualKey("VK_P",                              80);
ooif_helper.defineVirtualKey("VK_Q",                              81);
ooif_helper.defineVirtualKey("VK_R",                              82);
ooif_helper.defineVirtualKey("VK_S",                              83);
ooif_helper.defineVirtualKey("VK_T",                              84);
ooif_helper.defineVirtualKey("VK_U",                              85);
ooif_helper.defineVirtualKey("VK_V",                              86);
ooif_helper.defineVirtualKey("VK_W",                              87);
ooif_helper.defineVirtualKey("VK_X",                              88);
ooif_helper.defineVirtualKey("VK_Y",                              89);
ooif_helper.defineVirtualKey("VK_Z",                              90);
ooif_helper.defineVirtualKey("VK_OPEN_BRACKET",                   91);
ooif_helper.defineVirtualKey("VK_BACK_SLASH",  					  92);
ooif_helper.defineVirtualKey("VK_CLOSE_BRACKET",                  93);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD0",		      96,  0);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD1",		      97,  1);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD2",		      98,  2);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD3",		      99,  3);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD4",		      100, 4);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD5",		      101, 5);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD6",		      102, 6);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD7",		      103, 7);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD8",		      104, 8);
ooif_helper.defineVirtualKeyWithOffset("VK_NUMPAD9",		      105, 9);
ooif_helper.defineVirtualKeyWithOffset("VK_MULTIPLY",		      106, 10);
ooif_helper.defineVirtualKeyWithOffset("VK_ADD",			      107, 11);
ooif_helper.defineVirtualKeyWithOffset("VK_SEPARATER",		      108, 12);
ooif_helper.defineVirtualKeyWithOffset("VK_SUBTRACT",		      109, 13);
ooif_helper.defineVirtualKeyWithOffset("VK_DECIMAL",		      110, 14);
ooif_helper.defineVirtualKeyWithOffset("VK_DIVIDE",			      111, 15);
ooif_helper.defineVirtualKeyWithOffset("VK_F1",				      112, 16);
ooif_helper.defineVirtualKeyWithOffset("VK_F2",				      113, 17);
ooif_helper.defineVirtualKeyWithOffset("VK_F3",				      114, 18);
ooif_helper.defineVirtualKeyWithOffset("VK_F4",				      115, 19);
ooif_helper.defineVirtualKeyWithOffset("VK_F5",				      116, 20);
ooif_helper.defineVirtualKeyWithOffset("VK_F6",				      117, 21);
ooif_helper.defineVirtualKeyWithOffset("VK_F7",				      118, 22);
ooif_helper.defineVirtualKeyWithOffset("VK_F8",				      119, 23);
ooif_helper.defineVirtualKeyWithOffset("VK_F9",				      120, 24);
ooif_helper.defineVirtualKeyWithOffset("VK_F10",			      121, 25);
ooif_helper.defineVirtualKeyWithOffset("VK_F11",			      122, 26);
ooif_helper.defineVirtualKeyWithOffset("VK_F12",			      123, 27);
ooif_helper.defineVirtualKeyWithOffset("VK_DELETE",			      127, 28);
ooif_helper.defineVirtualKeyWithOffset("VK_NUM_LOCK",		      144, 29);
ooif_helper.defineVirtualKeyWithOffset("VK_SCROLL_LOCK",	      145, 30);
ooif_helper.defineVirtualKeyWithOffset("VK_PRINTSCREEN",	      154, 31);
ooif_helper.defineVirtualKeyWithOffset("VK_INSERT",			      155, 32);
ooif_helper.defineVirtualKeyWithOffset("VK_HELP",			      156, 33);
ooif_helper.defineVirtualKeyWithOffset("VK_META",			      157, 34);
ooif_helper.defineVirtualKeyWithOffset("VK_BACK_QUOTE",		      192, 35);
ooif_helper.defineVirtualKeyWithOffset("VK_QUOTE",			      222, 36);
ooif_helper.defineVirtualKeyWithOffset("VK_RED",			      403, 37);
ooif_helper.defineVirtualKeyWithOffset("VK_GREEN",			      404, 38);
ooif_helper.defineVirtualKeyWithOffset("VK_YELLOW",			      405, 39);
ooif_helper.defineVirtualKeyWithOffset("VK_BLUE",			      406, 40);
ooif_helper.defineVirtualKeyWithOffset("VK_GREY",			      407, 41);
ooif_helper.defineVirtualKeyWithOffset("VK_BROWN",			      408, 42);
ooif_helper.defineVirtualKeyWithOffset("VK_POWER",			      409, 43);
ooif_helper.defineVirtualKeyWithOffset("VK_DIMMER",			      410, 44);
ooif_helper.defineVirtualKeyWithOffset("VK_WINK",			      411, 45);
ooif_helper.defineVirtualKeyWithOffset("VK_REWIND",			      412, 46);
ooif_helper.defineVirtualKeyWithOffset("VK_STOP",			      413, 47);
ooif_helper.defineVirtualKeyWithOffset("VK_EJECT_TOGGLE",         414, 48);
ooif_helper.defineVirtualKeyWithOffset("VK_PLAY",                 415, 49);
ooif_helper.defineVirtualKeyWithOffset("VK_RECORD", 	          416, 50);
ooif_helper.defineVirtualKeyWithOffset("VK_FAST_FWD",             417, 51);
ooif_helper.defineVirtualKeyWithOffset("VK_PLAY_SPEED_UP",        418, 52);
ooif_helper.defineVirtualKeyWithOffset("VK_PLAY_SPEED_DOWN",      419, 53);
ooif_helper.defineVirtualKeyWithOffset("VK_PLAY_SPEED_RESET", 	  420, 54);
ooif_helper.defineVirtualKeyWithOffset("VK_RECORD_SPEED_NEXT",    421, 55);
ooif_helper.defineVirtualKeyWithOffset("VK_GO_TO_START",          422, 56);
ooif_helper.defineVirtualKeyWithOffset("VK_GO_TO_END",  		  423, 57);
ooif_helper.defineVirtualKeyWithOffset("VK_TRACK_PREV", 		  424, 58);
ooif_helper.defineVirtualKeyWithOffset("VK_TRACK_NEXT", 		  425, 59);
ooif_helper.defineVirtualKeyWithOffset("VK_RANDOM_TOGGLE", 		  426, 60);
ooif_helper.defineVirtualKeyWithOffset("VK_CHANNEL_UP",           427, 61);
ooif_helper.defineVirtualKeyWithOffset("VK_CHANNEL_DOWN",         428, 62);
ooif_helper.defineVirtualKeyWithOffset("VK_STORE_FAVORITE_0", 	  429, 63);
ooif_helper.defineVirtualKeyWithOffset("VK_STORE_FAVORITE_1",     430, 64);
ooif_helper.defineVirtualKeyWithOffset("VK_STORE_FAVORITE_2",     431, 65);
ooif_helper.defineVirtualKeyWithOffset("VK_STORE_FAVORITE_3",     432, 66);
ooif_helper.defineVirtualKeyWithOffset("VK_RECALL_FAVORITE_0",    433, 67);
ooif_helper.defineVirtualKeyWithOffset("VK_RECALL_FAVORITE_1",    434, 68);
ooif_helper.defineVirtualKeyWithOffset("VK_RECALL_FAVORITE_2",    435, 69);
ooif_helper.defineVirtualKeyWithOffset("VK_RECALL_FAVORITE_3",    436, 70);
ooif_helper.defineVirtualKeyWithOffset("VK_CLEAR_FAVORITE_0",     437, 71);
ooif_helper.defineVirtualKeyWithOffset("VK_CLEAR_FAVORITE_1",     438, 72);
ooif_helper.defineVirtualKeyWithOffset("VK_CLEAR_FAVORITE_2",     439, 73);
ooif_helper.defineVirtualKeyWithOffset("VK_CLEAR_FAVORITE_3",     440, 74);
ooif_helper.defineVirtualKeyWithOffset("VK_SCAN_CHANNELS_TOGGLE", 441, 75);
ooif_helper.defineVirtualKeyWithOffset("VK_PINP_TOGGLE",  		  442, 76);
ooif_helper.defineVirtualKeyWithOffset("VK_SPLIT_SCREEN_TOGGLE",  443, 77);
ooif_helper.defineVirtualKeyWithOffset("VK_DISPLAY_SWAP",         444, 78);
ooif_helper.defineVirtualKeyWithOffset("VK_SCREEN_MODE_NEXT",     445, 79);
ooif_helper.defineVirtualKeyWithOffset("VK_VIDEO_MODE_NEXT",      446, 80);
ooif_helper.defineVirtualKeyWithOffset("VK_VOLUME_UP", 			  447, 81);
ooif_helper.defineVirtualKeyWithOffset("VK_VOLUME_DOWN", 		  448, 82);
ooif_helper.defineVirtualKeyWithOffset("VK_MUTE", 				  449, 83);
ooif_helper.defineVirtualKeyWithOffset("VK_SURROUND_MODE_NEXT",   450, 84);
ooif_helper.defineVirtualKeyWithOffset("VK_BALANCE_RIGHT",        451, 85);
ooif_helper.defineVirtualKeyWithOffset("VK_BALANCE_LEFT", 		  452, 86);
ooif_helper.defineVirtualKeyWithOffset("VK_FADER_FRONT", 		  453, 87);
ooif_helper.defineVirtualKeyWithOffset("VK_FADER_REAR", 		  454, 88);
ooif_helper.defineVirtualKeyWithOffset("VK_BASS_BOOST_UP", 		  455, 89);
ooif_helper.defineVirtualKeyWithOffset("VK_BASS_BOOST_DOWN",      456, 90);
ooif_helper.defineVirtualKeyWithOffset("VK_INFO",                 457, 91);
ooif_helper.defineVirtualKeyWithOffset("VK_GUIDE", 				  458, 92);
ooif_helper.defineVirtualKeyWithOffset("VK_TELETEXT",             459, 93);
ooif_helper.defineVirtualKeyWithOffset("VK_SUBTITLE", 			  460, 94);
ooif_helper.defineVirtualKeyWithOffset("VK_BACK",                 461, 95);
ooif_helper.defineVirtualKeyWithOffset("VK_MENU", 				  462, 96);
ooif_helper.defineVirtualKeyWithOffset("VK_PLAY_PAUSE",           463, 97);

window.opera.addEventListener('BeforeEvent.keydown',  ooif_helper.translateVirtualKeyWithOffset, true);
window.opera.addEventListener('BeforeEvent.keypress', ooif_helper.translateVirtualKeyWithOffset, true);
window.opera.addEventListener('BeforeEvent.keyup',    ooif_helper.translateVirtualKeyWithOffset, true);



<!-- The following piece of code is required for XML StreamEvent support in HbbTV -->

HTMLObjectElement.prototype.addStreamEventListener = function(targetURL, eventName, listener)
{
    if (typeof(this.type) != 'string' || this.type != 'video/broadcast')
	    return;

    if (targetURL.indexOf('http://')<0 && targetURL.indexOf('https://')<0 && (targetURL.indexOf('dvb://')>=0 || window.location.toString().indexOf('dvb://')>= 0))
     	     return this.internalAddStreamEventListener(targetURL, eventName, listener);

    var xhr = new XMLHttpRequest();

    xhr.open("GET", targetURL, false);
    xhr.send(null);

    var parser = new DOMParser();
    var xdoc = parser.parseFromString(xhr.responseText, "text/xml");

    var dsmccObjects = xdoc.getElementsByTagName('dsmcc_object');
    if (dsmccObjects.length <= 0)
	return;

    var dsmccObject = dsmccObjects[0];
    var componentTag = dsmccObject.getAttribute('component_tag');
    if (!componentTag)
	return;

    var streamEventId = null;
    var streamEvents = dsmccObject.getElementsByTagName('stream_event');

    for (var i = 0; i < streamEvents.length; i++)
	if (eventName == streamEvents[i].getAttribute('stream_event_name'))
	    {
		var streamEventId = streamEvents[i].getAttribute('stream_event_id');
		break;
	    }

    if (!streamEventId)
	    return;

    return this.internalAddXMLStreamEventListener(eventName, parseInt(streamEventId), parseInt(componentTag), listener);
}
