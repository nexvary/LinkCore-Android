package com.fgmachines.rck;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Deliberately narrow grammar: one explicit outlet and one explicit ON/OFF action. */
public final class DirectVoiceCommand {
    public final int outlet;
    public final boolean on;
    private DirectVoiceCommand(int outlet, boolean on) { this.outlet = outlet; this.on = on; }
    public static DirectVoiceCommand parse(String speech) {
        if (speech == null || speech.length() > 160) return null;
        String text = Normalizer.normalize(speech.toLowerCase(Locale.ROOT), Normalizer.Form.NFD)
                .replaceAll("\\p{M}", "").replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
                .replace('١', '1').replace('٢', '2').replace('٣', '3').replace('٤', '4')
                .replace('۱', '1').replace('۲', '2').replace('۳', '3').replace('۴', '4')
                .replaceAll("[.,!?،؟]", " ").trim().replaceAll("\\s+", " ");
        // Full match rejects negation, two actions, two outlets, and uncertain phrases.
        Matcher en = Pattern.compile("(?:turn|switch) (on|off) (?:the )?(?:outlet|socket) (1|2|3|4|one|two|three|four)").matcher(text);
        Matcher enTail = Pattern.compile("(?:turn|switch) (?:the )?(?:outlet|socket) (1|2|3|4|one|two|three|four) (on|off)").matcher(text);
        if (en.matches()) return new DirectVoiceCommand(number(en.group(2)), en.group(1).equals("on"));
        if (enTail.matches()) return new DirectVoiceCommand(number(enTail.group(1)), enTail.group(2).equals("on"));
        Matcher ar = Pattern.compile("(شغل|شغلي|افتح|اطفي|اطفئ|اطف|اقفل|اغلق) (?:المخرج|مخرج|المنفذ|منفذ) (1|2|3|4|الاول|الثاني|التاني|الثالث|التالت|الرابع|واحد|اثنين|اتنين|ثلاثة|تلاتة|اربعة)").matcher(text);
        if (!ar.matches()) return null;
        String action = ar.group(1);
        return new DirectVoiceCommand(number(ar.group(2)), action.equals("شغل") || action.equals("شغلي") || action.equals("افتح"));
    }
    private static int number(String word) {
        switch (word) {
            case "1": case "one": case "الاول": case "واحد": return 1;
            case "2": case "two": case "الثاني": case "التاني": case "اثنين": case "اتنين": return 2;
            case "3": case "three": case "الثالث": case "التالت": case "ثلاثة": case "تلاتة": return 3;
            default: return 4;
        }
    }
}
