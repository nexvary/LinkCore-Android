import AVFoundation
import Speech
import SwiftUI
import FGLinkCore

@MainActor
final class SpeechInput: ObservableObject {
    @Published var listening = false
    @Published var transcript = ""
    @Published var error = ""
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapped = false
    private var stopTask: Task<Void, Never>?
    private var generation = 0

    func start(arabic: Bool) async {
        stop(); error = ""; transcript = ""
        let current = generation
        let authorized = await withCheckedContinuation { c in SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0 == .authorized) } }
        guard current == generation else { return }
        let microphone = await withCheckedContinuation { c in AVAudioSession.sharedInstance().requestRecordPermission { c.resume(returning: $0) } }
        guard current == generation else { return }
        guard authorized && microphone else { error = "Microphone / speech permission required — يلزم إذن الميكروفون والتعرف على الصوت"; return }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: arabic ? "ar-EG" : "en-US")), recognizer.isAvailable else {
            error = "Speech recognition unavailable / التعرف على الصوت غير متاح"; return
        }
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true)
            let request = SFSpeechAudioBufferRecognitionRequest()
            request.shouldReportPartialResults = true
            if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
            self.request = request
            let input = engine.inputNode
            let format = input.outputFormat(forBus: 0)
            guard format.sampleRate > 0, format.channelCount > 0 else { throw LinkError.unsupported }
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
            tapped = true; engine.prepare(); try engine.start(); listening = true
            task = recognizer.recognitionTask(with: request) { [weak self] result, failure in Task { @MainActor in
                guard let self, current == self.generation else { return }
                if let result { self.transcript = result.bestTranscription.formattedString }
                if result?.isFinal == true || failure != nil {
                    if failure != nil && self.transcript.isEmpty { self.error = "Speech recognition failed / تعذر التعرف على الصوت" }
                    self.stop()
                }
            } }
            stopTask = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 12_000_000_000)
                guard !Task.isCancelled else { return }; self?.stop()
            }
        } catch { self.error = error.localizedDescription; stop() }
    }
    func stop() {
        generation += 1
        stopTask?.cancel(); stopTask = nil
        engine.stop(); if tapped { engine.inputNode.removeTap(onBus: 0); tapped = false }
        request?.endAudio(); task?.cancel(); task = nil; request = nil; listening = false
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
}
