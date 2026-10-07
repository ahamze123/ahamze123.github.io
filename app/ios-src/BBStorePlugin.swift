import Foundation
import Capacitor
import StoreKit

// Block Buddies' own bridge to the App Store (StoreKit 2), and a second copy of the save.
// The game calls it with Capacitor.nativePromise('BBStore', method, options):
//   products {ids}     -> {products: [{id, title, desc, price}]}        (price is ready to show, like "$3.99")
//   buy {id}           -> {ok: true, id} | {ok: false, cancelled: true} | {ok: false, pending: true}
//   owned {id}         -> {ids: [...], revoked: [...]}                   (what this Apple Account owns now)
//   restore {}         -> {ids: [...]}                                   (asks the App Store to sync first)
//   backupWrite {data} -> {ok: true}                                     (Application Support/bb_backup.json)
//   backupRead {}      -> {data: "..."} or {}
// Event 'owned' {id, revoked}: a purchase that arrives later (Ask to Buy, Family Sharing) or a refund.
// The BBTEST lines are for the simulator check in the GitHub workflow.
@objc(BBStorePlugin)
public class BBStorePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "BBStorePlugin"
    public let jsName = "BBStore"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "products", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "buy", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "owned", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "restore", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "backupWrite", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "backupRead", returnType: CAPPluginReturnPromise)
    ]
    private var updates: Task<Void, Never>?

    @objc override public func load() {
        NSLog("BBTEST BBStore ready")
        updates = Task.detached { [weak self] in
            for await result in Transaction.updates {
                guard case .verified(let t) = result else { continue }
                await t.finish()
                let data: [String: Any] = ["id": t.productID, "revoked": t.revocationDate != nil]
                DispatchQueue.main.async { self?.notifyListeners("owned", data: data) }
            }
        }
    }

    deinit { updates?.cancel() }

    private static func entitlements() async -> [String] {
        var ids: [String] = []
        for await r in Transaction.currentEntitlements {
            if case .verified(let t) = r, t.revocationDate == nil { ids.append(t.productID) }
        }
        return ids
    }

    @objc func products(_ call: CAPPluginCall) {
        let ids = call.getArray("ids", String.self) ?? []
        Task {
            do {
                let list = try await Product.products(for: ids)
                NSLog("BBTEST BBStore products %ld", list.count)
                let out: [[String: Any]] = list.map { ["id": $0.id, "title": $0.displayName, "desc": $0.description, "price": $0.displayPrice] }
                call.resolve(["products": out])
            } catch {
                NSLog("BBTEST BBStore products error %@", error.localizedDescription)
                call.reject(error.localizedDescription)
            }
        }
    }

    @objc func buy(_ call: CAPPluginCall) {
        guard let id = call.getString("id") else { call.reject("no product id"); return }
        Task { @MainActor in
            do {
                guard let product = try await Product.products(for: [id]).first else { call.reject("not in the App Store"); return }
                let result = try await product.purchase()
                switch result {
                case .success(let verification):
                    switch verification {
                    case .verified(let t):
                        await t.finish()
                        NSLog("BBTEST BBStore bought %@", t.productID)
                        call.resolve(["ok": true, "id": t.productID])
                    case .unverified(_, let err):
                        call.reject("not verified: " + err.localizedDescription)
                    }
                case .userCancelled:
                    call.resolve(["ok": false, "cancelled": true])
                case .pending:
                    call.resolve(["ok": false, "pending": true])
                @unknown default:
                    call.resolve(["ok": false])
                }
            } catch {
                NSLog("BBTEST BBStore buy error %@", error.localizedDescription)
                call.reject(error.localizedDescription)
            }
        }
    }

    @objc func owned(_ call: CAPPluginCall) {
        let pid = call.getString("id")
        Task {
            let ids = await BBStorePlugin.entitlements()
            var revoked: [String] = []
            if let pid = pid, let latest = await Transaction.latest(for: pid), case .verified(let t) = latest, t.revocationDate != nil {
                revoked.append(pid)
            }
            NSLog("BBTEST BBStore owned %ld", ids.count)
            call.resolve(["ids": ids, "revoked": revoked])
        }
    }

    @objc func restore(_ call: CAPPluginCall) {
        Task {
            do { try await AppStore.sync() } catch { NSLog("BBTEST BBStore sync %@", error.localizedDescription) }
            let ids = await BBStorePlugin.entitlements()
            NSLog("BBTEST BBStore restore %ld", ids.count)
            call.resolve(["ids": ids])
        }
    }

    // ---------- the second copy of the save (Application Support is kept in the iPad's iCloud backup) ----------
    private func backupURL() throws -> URL {
        let dir = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        return dir.appendingPathComponent("bb_backup.json")
    }

    @objc func backupWrite(_ call: CAPPluginCall) {
        guard let data = call.getString("data"), !data.isEmpty else { call.reject("nothing to keep"); return }
        do {
            try data.write(to: try backupURL(), atomically: true, encoding: .utf8)
            NSLog("BBTEST BBStore backup %ld", data.utf8.count)
            call.resolve(["ok": true])
        } catch {
            call.reject(error.localizedDescription)
        }
    }

    @objc func backupRead(_ call: CAPPluginCall) {
        do {
            let url = try backupURL()
            if FileManager.default.fileExists(atPath: url.path) {
                let data = try String(contentsOf: url, encoding: .utf8)
                NSLog("BBTEST BBStore read %ld", data.utf8.count)
                call.resolve(["data": data])
            } else {
                call.resolve()
            }
        } catch {
            call.reject(error.localizedDescription)
        }
    }
}
