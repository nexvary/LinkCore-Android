import XCTest

final class FGLinkUITests: XCTestCase {
    func testArabicEnglishSetupAndLogin() {
        let app = XCUIApplication()
        app.launchArguments = ["-fg.language", "ar"]
        app.launch()
        XCTAssertTrue(app.buttons["languageButton"].waitForExistence(timeout: 10))
        attach(app, "Arabic home")
        app.buttons["languageButton"].tap()
        XCTAssertTrue(app.staticTexts["My strips"].firstMatch.waitForExistence(timeout: 3))
        app.segmentedControls["routePicker"].buttons["Direct VPS"].tap()
        XCTAssertTrue(app.secureTextFields["Password"].exists)
        XCTAssertFalse(app.buttons["signInButton"].isEnabled)
        XCTAssertFalse(app.staticTexts["Owner"].exists)
        attach(app, "English VPS account")
        app.tabBars.buttons["Add"].tap()
        XCTAssertTrue(app.textFields["Home Wi-Fi SSID"].waitForExistence(timeout: 3))
        let send = app.buttons["Join Wi-Fi and configure"]
        XCTAssertFalse(send.isEnabled)
        attach(app, "Setup consent")
        app.tabBars.buttons["About"].tap()
        XCTAssertTrue(app.staticTexts["FG Link 2.1.2"].waitForExistence(timeout: 3))
        attach(app, "About")
    }
    private func attach(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
