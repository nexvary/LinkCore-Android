import Foundation

public struct VoiceCommand: Equatable, Identifiable {
    public let outlet: Int
    public let on: Bool
    public var id: String { "\(outlet):\(on)" }
    public static func parse(_ speech: String) -> VoiceCommand? {
        guard speech.count <= 160 else { return nil }
        var text = speech.lowercased().decomposedStringWithCanonicalMapping
        text = String(text.unicodeScalars.filter { !CharacterSet.nonBaseCharacters.contains($0) })
        for (a, b) in [("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("١", "1"), ("٢", "2"), ("٣", "3"), ("٤", "4"),
                       ("۱", "1"), ("۲", "2"), ("۳", "3"), ("۴", "4")] { text = text.replacingOccurrences(of: a, with: b) }
        text = text.replacingOccurrences(of: "[.,!?،؟]", with: " ", options: .regularExpression)
        let words = text.split(whereSeparator: { $0.isWhitespace }).map(String.init)
        let numbers = ["1": 1, "one": 1, "الاول": 1, "واحد": 1, "2": 2, "two": 2, "الثاني": 2,
                       "التاني": 2, "اثنين": 2, "اتنين": 2, "3": 3, "three": 3, "الثالث": 3,
                       "التالت": 3, "ثلاثة": 3, "تلاتة": 3, "4": 4, "four": 4, "الرابع": 4, "اربعة": 4]
        if words.count == 3, ["المخرج", "مخرج", "المنفذ", "منفذ"].contains(words[1]),
           ["شغل", "شغلي", "افتح", "اطفي", "اطفئ", "اطف", "اقفل", "اغلق"].contains(words[0]), let n = numbers[words[2]] {
            return VoiceCommand(outlet: n, on: ["شغل", "شغلي", "افتح"].contains(words[0]))
        }
        guard words.first == "turn" || words.first == "switch" else { return nil }
        var tail = Array(words.dropFirst())
        if tail.count == 4 {
            if ["on", "off"].contains(tail[0]), tail[1] == "the" { tail.remove(at: 1) }
            else if tail[0] == "the", ["outlet", "socket"].contains(tail[1]) { tail.removeFirst() }
        }
        guard tail.count == 3 else { return nil }
        if ["on", "off"].contains(tail[0]), ["outlet", "socket"].contains(tail[1]), let n = numbers[tail[2]] {
            return VoiceCommand(outlet: n, on: tail[0] == "on")
        }
        if ["outlet", "socket"].contains(tail[0]), let n = numbers[tail[1]], ["on", "off"].contains(tail[2]) {
            return VoiceCommand(outlet: n, on: tail[2] == "on")
        }
        return nil
    }
}
