import SwiftUI

@main
@MainActor
struct FGLinkApp: App {
    @StateObject private var model = LinkModel()
    @Environment(\.scenePhase) private var phase
    var body: some Scene {
        WindowGroup {
            ContentView().environmentObject(model)
                .environment(\.layoutDirection, model.arabic ? .rightToLeft : .leftToRight)
                .environment(\.locale, Locale(identifier: model.arabic ? "ar" : "en"))
                .preferredColorScheme(.dark)
                .onAppear { model.activate(true) }
                .onChange(of: phase) { model.activate($0 == .active) }
        }
    }
}
