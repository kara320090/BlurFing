package com.blurfing.app.experimental

import kotlinx.serialization.json.Json

/** Serialization rejects unknown fields but otherwise overwrites duplicate keys. Reject ambiguity first. */
internal object ExperimentalJsonGuard {
    fun verify(text: String) {
        require(text.length.toLong()<=ExperimentalPhotoRepository.MAX_RESPONSE_BYTES)
        var at=0;var nodes=0
        fun space() { while(at<text.length && text[at] in " \t\r\n")at++ }
        fun string(key: Boolean): String? {
            require(at<text.length && text[at]=='"');val start=at++
            while(at<text.length) {
                val c=text[at++]
                if(c=='"') {
                    if(!key)return null
                    require(at-start<=512)
                    return Json.decodeFromString<String>(text.substring(start,at))
                }
                require(c.code>=32)
                if(c=='\\') {
                    require(at<text.length)
                    when(text[at++]) {
                        '"','\\','/','b','f','n','r','t'->Unit
                        'u'->{require(at+4<=text.length && text.substring(at,at+4).all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' });at+=4}
                        else->throw IllegalArgumentException("invalid JSON escape")
                    }
                }
                if(key)require(at-start<=512)
            };throw IllegalArgumentException("unfinished JSON string")
        }
        lateinit var value: (Int)->Unit
        value={ depth ->
            require(depth<=32 && ++nodes<=10000);space();require(at<text.length)
            when(text[at]) {
                '{'->{at++;space();val keys=HashSet<String>()
                    if(at<text.length && text[at]=='}')at++ else while(true) {
                        space();val key=string(true)!!;require(keys.size<128 && keys.add(key));space();require(at<text.length && text[at++]==':')
                        value(depth+1);space();require(at<text.length);val end=text[at++];if(end=='}')break;require(end==',')
                    }
                }
                '['->{at++;space();var count=0
                    if(at<text.length && text[at]==']')at++ else while(true) {
                        require(++count<=1024);value(depth+1);space();require(at<text.length);val end=text[at++];if(end==']')break;require(end==',')
                    }
                }
                '"'->string(false)
                else->{val start=at;while(at<text.length && text[at] !in ",]} \t\r\n")at++;require(at>start)}
            }
            Unit
        }
        value(0);space();require(at==text.length)
    }
}
