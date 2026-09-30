package com.fgmachines.rck;
import org.junit.Test;
import static org.junit.Assert.*;
public class DirectVoiceCommandTest {
    @Test public void arabicAndEnglishActions() {
        for (String text : new String[]{"شغّل المخرج الأول", "افتح مخرج ١", "Turn on outlet one", "switch outlet 1 on"}) {
            DirectVoiceCommand c = DirectVoiceCommand.parse(text); assertNotNull(text, c); assertEquals(1,c.outlet); assertTrue(c.on);
        }
        for (String text : new String[]{"اطفي المخرج الرابع", "أطفئ المخرج ٤", "اغلق منفذ اربعة", "Turn off the socket four"}) {
            DirectVoiceCommand c = DirectVoiceCommand.parse(text); assertNotNull(text,c); assertEquals(4,c.outlet); assertFalse(c.on);
        }
    }
    @Test public void refuseAmbiguousDangerousAndUnsupported() {
        for (String text : new String[]{"لا تشغل المخرج الاول", "don't turn on outlet one", "turn on all outlets", "turn on outlet 5", "شغل المخرج الاول والثاني", "turn on outlet one and off outlet two", "toggle outlet 1", "maybe turn on outlet one", "", "شغل التلفزيون"}) assertNull(text,DirectVoiceCommand.parse(text));
        assertNull(DirectVoiceCommand.parse(null));
    }
    @Test public void secondThirdAndArabicDigits() {
        assertEquals(2,DirectVoiceCommand.parse("اقفل المخرج التاني").outlet);
        assertEquals(3,DirectVoiceCommand.parse("شغل المخرج ٣").outlet);
    }
}
