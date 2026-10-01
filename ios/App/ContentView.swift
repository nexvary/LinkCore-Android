import SwiftUI
import FGLinkCore

private let navy = Color(red: 0.035, green: 0.065, blue: 0.085)
private let cyan = Color(red: 0.05, green: 0.85, blue: 0.95)
private let green = Color(red: 0.35, green: 1, blue: 0.15)

@MainActor
struct ContentView: View {
    @EnvironmentObject var model: LinkModel
    @State private var username = ""
    @State private var password = ""
    @State private var shareCode = ""
    var body: some View {
        TabView {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        HStack(spacing: 16) {
                            Image("Brand").resizable().frame(width: 64, height: 64).clipShape(RoundedRectangle(cornerRadius: 16))
                            VStack(alignment: .leading) { Text("FG Link").font(.largeTitle.bold()); Text("2.1.2 · iOS").foregroundStyle(.secondary) }
                        }
                        Picker(model.t("الاتصال", "Connection"), selection: Binding(get: { model.route }, set: { model.switchRoute($0) })) {
                            Text(model.t("محلي / LAN", "Local / LAN")).tag(LinkRoute.local)
                            Text("LAN / VPN").tag(LinkRoute.vpn)
                            Text("Direct VPS").tag(LinkRoute.vps)
                        }.pickerStyle(.segmented).accessibilityIdentifier("routePicker")
                        if model.route == .vps && !model.signedIn { login }
                        if model.route == .vpn && !model.signedIn {
                            VStack(alignment: .leading, spacing: 14) {
                                Text(model.t("اتصال LAN / ZeroTier", "LAN / ZeroTier connection")).font(.title2.bold())
                                Text(model.t("أدخل رمز المشاركة من تطبيق المتحكم. عند استخدام ZeroTier، اتصل بالشبكة من تطبيق ZeroTier أولًا.", "Enter the controller app's share code. For ZeroTier, join your network using the ZeroTier app first."))
                                SecureField("FGRCK1|…", text: $shareCode).textInputAutocapitalization(.never).autocorrectionDisabled().textFieldStyle(.roundedBorder)
                                Button(model.t("اتصال", "Connect")) {
                                    let code = shareCode; shareCode = ""; Task { await model.connectShare(code) }
                                }.buttonStyle(.borderedProminent).disabled(shareCode.isEmpty || model.busy)
                            }.padding(18).card()
                        }
                        if model.route == .local {
                            Text(model.t("اتصال محلي على المنفذ 10086. يجب ضبط عنوان المتحكم داخل المشترك. التحكم المحلي يعمل أثناء فتح التطبيق؛ استخدم VPS للتحكم المستقل عن الهاتف.",
                                         "Local controller on port 10086. Configure the strip with this phone's controller IP. Local control operates while the app is open; use VPS for control independent of the phone."))
                                .foregroundStyle(.secondary).font(.body)
                        }
                        HStack {
                            Text(model.t("مشتركاتي", "My strips")).font(.title2.bold())
                            Spacer()
                            Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise").font(.title2) }
                                .accessibilityLabel(model.t("تحديث", "Refresh"))
                        }
                        if model.devices.isEmpty {
                            VStack(spacing: 12) {
                                Image(systemName: "powerplug").font(.system(size: 42)).foregroundStyle(cyan)
                                Text(model.t("لا توجد مشتركات متصلة", "No connected strips")).font(.headline)
                                Text(model.t("أضف إعدادات الشبكة أو سجّل الدخول إلى حسابك.", "Configure a strip or sign into your account.")).foregroundStyle(.secondary)
                            }.frame(maxWidth: .infinity).padding(24).card()
                        }
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                            ForEach(model.devices) { strip in
                                NavigationLink { StripDetail(mac: strip.mac) } label: {
                                    VStack(alignment: .leading, spacing: 12) {
                                        HStack { Image(systemName: "powerplug.fill").font(.title); Spacer(); Circle().fill(strip.connected ? green : .gray).frame(width: 10, height: 10) }
                                        Text(strip.mac).font(.system(.callout, design: .monospaced)).minimumScaleFactor(0.6).lineLimit(1).environment(\.layoutDirection, .leftToRight)
                                        Text(strip.connected ? model.t("متصل", "Online") : model.t("غير متصل", "Offline")).foregroundStyle(strip.connected ? green : .secondary)
                                    }.padding(16).frame(maxWidth: .infinity, alignment: .leading).card()
                                }.simultaneousGesture(TapGesture().onEnded { model.selectedMAC = strip.mac })
                            }
                        }
                        if !model.message.isEmpty { Text(model.message).foregroundStyle(cyan).accessibilityIdentifier("statusMessage") }
                        NavigationLink { SetupView() } label: { Label(model.t("إعداد مشترك جديد", "Configure a new strip"), systemImage: "plus.circle.fill").frame(maxWidth: .infinity) }
                            .buttonStyle(.borderedProminent)
                        if model.signedIn { Button(model.t("تسجيل الخروج", "Sign out"), role: .destructive) { Task { await model.logout() } } }
                    }.padding(18)
                }.background(navy).navigationTitle(model.t("الرئيسية", "Home"))
                    .toolbar { languageButton }
            }.tabItem { Label(model.t("مشتركاتي", "My strips"), systemImage: "powerplug.fill") }
            NavigationStack { SetupView().toolbar { languageButton } }.tabItem { Label(model.t("إضافة", "Add"), systemImage: "plus.circle.fill") }
            NavigationStack { NotificationsView().toolbar { languageButton } }.tabItem { Label(model.t("التنبيهات", "Alerts"), systemImage: "bell.fill") }
            NavigationStack { AboutView().toolbar { languageButton } }.tabItem { Label(model.t("عنا", "About"), systemImage: "info.circle.fill") }
        }.tint(cyan)
            .task {
                while !Task.isCancelled {
                    await model.refresh()
                    do { try await Task.sleep(nanoseconds: 3_000_000_000) } catch { return }
                }
            }
    }
    private var languageButton: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            Button(model.arabic ? "English" : "العربية") { model.language = model.arabic ? "en" : "ar" }.accessibilityIdentifier("languageButton")
        }
    }
    private var login: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(model.t("حساب المشترك", "Subscriber account")).font(.title2.bold())
            TextField(model.t("الخادم", "Server"), text: $model.server).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField(model.t("اسم المستخدم", "Username"), text: $username).textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
            SecureField(model.t("كلمة المرور", "Password"), text: $password).textContentType(.password)
            Button {
                let secret = password; password = ""
                Task { await model.login(username: username, password: secret) }
            } label: {
                HStack { if model.busy { ProgressView() }; Text(model.t("تسجيل الدخول", "Sign in")).frame(maxWidth: .infinity) }
            }.buttonStyle(.borderedProminent).disabled(model.busy || username.isEmpty || password.isEmpty).accessibilityIdentifier("signInButton")
        }.textFieldStyle(.roundedBorder).padding(18).card()
    }
}

@MainActor
struct StripDetail: View {
    @EnvironmentObject var model: LinkModel
    let mac: String
    @State private var voicePresented = false
    private var strip: Strip? { model.devices.first { $0.mac == mac } }
    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                Text(mac).font(.system(.headline, design: .monospaced)).environment(\.layoutDirection, .leftToRight)
                Text(strip?.connected == true ? model.t("متصل", "Online") : model.t("غير متصل", "Offline")).foregroundStyle(strip?.connected == true ? green : .gray)
                ForEach(1...4, id: \.self) { channel in
                    let outlet = strip?.outlets.first { $0.channel == channel }
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Image(systemName: "powerplug.fill").font(.title2).foregroundStyle(outlet?.relay == "on" ? green : cyan)
                            Text(model.t("المخرج \(channel)", "Outlet \(channel)")).font(.title3.bold())
                            Spacer()
                            Text(state(outlet?.relay)).foregroundStyle(.secondary).accessibilityIdentifier("outlet\(channel)State")
                        }
                        HStack {
                            telemetry(outlet?.powerW, suffix: "W"); Spacer()
                            telemetry(outlet?.energyWh.map { $0 / 1000 }, suffix: "kWh"); Spacer()
                            telemetry(outlet?.temperatureC, suffix: "°C")
                        }.font(.callout)
                        HStack(spacing: 12) {
                            control(channel, on: true); control(channel, on: false)
                        }
                    }.padding(18).card()
                }
                Text(model.t("منافذ USB للشحن؛ التحكم المستقل بها غير مُثبت.", "USB ports provide charging; independent switching is unverified.")).foregroundStyle(.secondary)
                Button { voicePresented = true } label: { Label(model.t("التحكم بالصوت", "Voice control"), systemImage: "mic.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).disabled(strip?.connected != true || model.pendingMAC != nil)
                if !model.message.isEmpty { Text(model.message).foregroundStyle(cyan) }
                NavigationLink(model.t("سجل الطاقة خلال الجلسة", "Energy history this session")) { HistoryView(mac: mac) }
            }.padding(18)
        }.background(navy).navigationTitle(model.t("التحكم", "Control"))
            .sheet(isPresented: $voicePresented) { VoiceView(mac: mac) }
    }
    private func control(_ channel: Int, on: Bool) -> some View {
        Button { Task { await model.setOutlet(mac: mac, channel: channel, on: on) } } label: {
            Label(on ? model.t("تشغيل", "On") : model.t("إيقاف", "Off"), systemImage: on ? "power" : "power.circle")
                .frame(maxWidth: .infinity).padding(.vertical, 5)
        }.buttonStyle(.bordered).tint(on ? green : cyan)
            .disabled(strip?.canControl(channel) != true || model.pendingMAC != nil)
            .accessibilityIdentifier("outlet\(channel)\(on ? "On" : "Off")")
    }
    private func telemetry(_ number: Double?, suffix: String) -> some View {
        Text(number.map { String(format: "%.2f %@", $0, suffix) } ?? "— \(suffix)").environment(\.layoutDirection, .leftToRight)
    }
    private func state(_ value: String?) -> String {
        if value == "on" { return model.t("يعمل", "On") }
        if value == "off" { return model.t("متوقف", "Off") }
        return model.t("غير معروف", "Unknown")
    }
}

@MainActor
struct VoiceView: View {
    @EnvironmentObject var model: LinkModel
    @Environment(\.dismiss) var dismiss
    @Environment(\.scenePhase) var phase
    @StateObject private var speech = SpeechInput()
    @State private var pending: VoiceCommand?
    let mac: String
    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Image(systemName: "mic.circle.fill").font(.system(size: 90)).foregroundStyle(cyan)
                Text(model.t("مثال: شغل المخرج واحد", "Example: turn on outlet one")).font(.title3)
                Text(speech.transcript).font(.title2).frame(minHeight: 80)
                Text(speech.error).foregroundStyle(.orange)
                Button(speech.listening ? model.t("إيقاف الاستماع", "Stop listening") : model.t("ابدأ الاستماع", "Start listening")) {
                    if speech.listening { speech.stop() } else { Task { await speech.start(arabic: model.arabic) } }
                }.buttonStyle(.borderedProminent)
                Button(model.t("مراجعة الأمر", "Review command")) {
                    speech.stop(); pending = VoiceCommand.parse(speech.transcript)
                    if pending == nil { speech.error = model.t("اذكر مخرجًا واحدًا وأمرًا واضحًا بالتشغيل أو الإيقاف.", "Specify one outlet and an explicit on/off action.") }
                }.buttonStyle(.bordered).disabled(speech.transcript.isEmpty)
                Spacer()
            }.padding(24).background(navy).navigationTitle(model.t("الصوت", "Voice"))
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(model.t("رجوع", "Back")) { dismiss() } } }
        }.onDisappear { speech.stop() }
            .onChange(of: phase) { if $0 != .active { speech.stop() } }
            .alert(item: $pending) { command in
                Alert(title: Text(model.t("تأكيد التنفيذ", "Confirm command")),
                      message: Text("\(mac)\n\(model.t("المخرج", "Outlet")) \(command.outlet) · \(command.on ? model.t("تشغيل", "On") : model.t("إيقاف", "Off"))"),
                      primaryButton: .default(Text(model.t("إرسال", "Send"))) { Task { await model.setOutlet(mac: mac, channel: command.outlet, on: command.on); dismiss() } },
                      secondaryButton: .cancel(Text(model.t("إلغاء", "Cancel"))))
            }
    }
}

@MainActor
struct SetupView: View {
    @EnvironmentObject var model: LinkModel
    @StateObject private var setup = StripSetup()
    @State private var ap = "TONLY_TAP_"
    @State private var ssid = ""
    @State private var password = ""
    @State private var controller = ""
    @State private var vps = false
    @State private var consent = false
    @State private var setupTask: Task<Void, Never>?
    var body: some View {
        Form {
            Section(model.t("طريقة الاتصال", "Connection method")) {
                Toggle("Direct VPS", isOn: $vps)
                if vps {
                    Button(model.t("استخراج عنوان خادم VPS", "Resolve VPS address")) {
                        setupTask = Task {
                            do { controller = try await setup.resolveVPS(model.server) }
                            catch { setup.status = error.localizedDescription }
                        }
                    }
                }
                TextField(model.t("IPv4 المتحكم", "Controller IPv4"), text: $controller).keyboardType(.decimalPad)
                Text(model.t("للاتصال المحلي، أدخل IPv4 الهاتف على شبكة المنزل. عنوان VPS يُستخرج قبل الاتصال بشبكة المشترك.",
                             "For local control, enter the phone's home-network IPv4. Resolve the VPS address before joining the strip's setup Wi-Fi."))
            }
            Section(model.t("شبكة المشترك وشبكة المنزل", "Strip and home Wi-Fi")) {
                TextField("TONLY_TAP_XXXXXXX", text: $ap).textInputAutocapitalization(.characters).autocorrectionDisabled()
                TextField(model.t("اسم شبكة المنزل", "Home Wi-Fi SSID"), text: $ssid).autocorrectionDisabled()
                SecureField(model.t("كلمة مرور شبكة المنزل", "Home Wi-Fi password"), text: $password)
                if let derived = try? Wire.setupPassword(ap) { Text("\(model.t("كلمة مرور المشترك", "Strip password")): \(derived)").textSelection(.enabled) }
            }
            Section {
                Toggle(model.t("أوافق على تغيير إعدادات شبكة المشترك", "I agree to change the strip's network settings"), isOn: $consent)
                Button(model.t("اتصال تلقائي وإعداد", "Join Wi-Fi and configure")) { configure(auto: true) }.disabled(!consent || setup.busy)
                Button(model.t("أنا متصل بشبكة المشترك — إرسال الإعدادات", "Already on strip Wi-Fi — send settings")) { configure(auto: false) }.disabled(!consent || setup.busy)
                Text(model.t("يمكنك الاتصال بشبكة المشترك يدويًا من إعدادات Wi-Fi في الآيفون ثم استخدام الخيار الثاني.",
                             "You can manually join the strip's Wi-Fi in iPhone Settings and use the second option."))
                Text(model.t("إعداد الشبكة لا يُنشئ حسابًا أو يمنح صلاحية تحكم. يجب ربط المشترك بحسابك من لوحة الإدارة.",
                             "Network setup does not create an account or control grant. Assign the strip to your account in the administration panel."))
                if setup.busy { ProgressView(); Button(model.t("إلغاء", "Cancel"), role: .cancel) { setupTask?.cancel(); setup.cancel() } }
                Text(setup.status).foregroundStyle(cyan)
            }
        }.navigationTitle(model.t("إعداد مشترك", "Strip setup"))
            .onDisappear { setupTask?.cancel(); setup.cancel(); password = "" }
    }
    private func configure(auto: Bool) {
        setupTask = Task {
            do { try await setup.configure(ap: ap, ssid: ssid, password: password, controller: controller, joinAutomatically: auto); password = "" }
            catch { setup.status = error.localizedDescription }
        }
    }
}

@MainActor
struct NotificationsView: View {
    @EnvironmentObject var model: LinkModel
    var body: some View {
        Form {
            if model.route == .vps && model.signedIn {
                Section(model.t("تنبيهات البريد", "Email alerts")) {
                    Toggle(model.t("تفعيل التنبيهات", "Enable alerts"), isOn: $model.email.enabled).disabled(model.email.smtpReady != true)
                    TextField(model.t("البريد الإلكتروني", "Email"), text: $model.email.email).keyboardType(.emailAddress).textInputAutocapitalization(.never)
                    Stepper("\(model.t("القدرة", "Power")): \(model.email.powerW) W", value: $model.email.powerW, in: 100...10000, step: 100)
                    Stepper("\(model.t("الحرارة", "Temperature")): \(model.email.temperatureC) °C", value: $model.email.temperatureC, in: 30...120)
                    Button(model.t("حفظ", "Save")) { Task { await model.saveEmail() } }
                    Button(model.t("إرسال رسالة اختبار", "Send test email")) { Task { await model.saveEmail(test: true) } }.disabled(model.email.smtpReady != true)
                }.disabled(model.busy || !model.emailLoaded)
                if model.emailLoaded && model.email.smtpReady != true {
                    Text(model.t("خدمة إرسال البريد غير جاهزة على الخادم.", "Email delivery is not configured on the server."))
                }
                Button(model.t("تحميل الإعدادات", "Load settings")) { Task { await model.loadEmail() } }
            } else { Text(model.t("سجّل الدخول إلى VPS لإعداد تنبيهات البريد.", "Sign into VPS to configure email alerts.")) }
            Text(model.message).foregroundStyle(cyan)
        }.navigationTitle(model.t("التنبيهات", "Alerts")).task { await model.loadEmail() }
    }
}

@MainActor
struct HistoryView: View {
    @EnvironmentObject var model: LinkModel
    let mac: String
    var body: some View {
        List {
            let samples = model.history.filter { $0.mac == mac }
            if samples.isEmpty { Text(model.t("لم تصل قياسات بعد", "No measurements received yet")) }
            ForEach(samples.reversed()) { sample in
                HStack { Text(sample.date, style: .time); Spacer(); Text(String(format: "%.2f W", sample.watts)) }
            }
        }.navigationTitle(model.t("سجل الجلسة", "Session history"))
    }
}

@MainActor
struct AboutView: View {
    @EnvironmentObject var model: LinkModel
    var body: some View {
        List {
            Section {
                Image("Brand").resizable().scaledToFit().frame(height: 140).frame(maxWidth: .infinity)
                Text("FG Link 2.1.2").font(.title2.bold())
                Text("FG Machines · Alaa Mohamed")
                Text(model.t("التحكم المحلي وDirect VPS في المشتركات الكورية المتوافقة.", "Local and Direct VPS control for compatible Korean power strips."))
            }
            Section(model.t("روابط رسمية", "Official links")) {
                Link("FG Machines", destination: URL(string: "https://www.facebook.com/share/1T7r3WpH8Y/")!)
                Link(model.t("المطور", "Developer"), destination: URL(string: "https://www.facebook.com/share/1EKVAyZZ2C/")!)
                Link("fgmachines.org", destination: URL(string: "https://fgmachines.org")!)
            }
            Section(model.t("المنزل الذكي", "Smart home")) {
                Text(model.t("يمكن لتكامل Home Assistant الحالي العمل من الخادم بصورة مستقلة عن نسخة الآيفون. ربط Google Home يحتاج إعداد التكامل على الخادم.",
                             "The existing Home Assistant integration can operate from the server independently of the iPhone app. Google Home requires server-side integration setup."))
                Link("Home Assistant", destination: URL(string: "https://www.home-assistant.io")!)
            }
            Section(model.t("حالة نسخة iOS", "iOS build status")) {
                Text(model.t("نسخة قيد التطوير والاختبار. إعداد Wi-Fi والتشغيل على الجهاز الحقيقي لم يُختبرا بعد.", "Development build. Wi-Fi provisioning and physical-device operation have not yet been verified."))
            }
        }.navigationTitle(model.t("عنا", "About"))
    }
}

private extension View {
    func card() -> some View {
        self.background(Color(red: 0.07, green: 0.11, blue: 0.15))
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.white.opacity(0.35), lineWidth: 1))
    }
}
