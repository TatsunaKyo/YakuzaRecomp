// SPDX-License-Identifier: GPL-3.0-or-later
// Original-free producer/presentation contention: no window or guest program.
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
#include <memory>
#include <stdexcept>

using namespace std::chrono_literals;
struct Gate {
    std::promise<void> entered, release;
    std::shared_future<void> released = release.get_future().share();
    void wait() { entered.set_value(); released.wait(); }
    void await() {
        if (entered.get_future().wait_for(5s) != std::future_status::ready)
            throw std::runtime_error("Controlled backend did not reach its gate");
    }
};
class Backend : public GSRasterBackend {
public:
    Gate *writeGate = nullptr, *presentGate = nullptr, *snapshotGate = nullptr;
    std::atomic<unsigned> presentations{0}, writes{0};
    void Initialize(uint8_t*, uint32_t) override {}
    void Reset() override {}
    void Submit(const GSPrimitiveBatch&) override {}
    void LoadClut(const GSTex0Reg&, const GSTexClutReg&) override {}
    void BeginTransfer(const GSTransferCommand&) override {}
    void UploadImage(const uint8_t*, uint32_t) override {}
    void Flush() override {}
    void TextureFlush() override {}
    void Sync(GSSyncReason) override {}
    PresentationFrame Present(const GSPresentationRequest&) override {
        if (presentGate) presentGate->wait();
        PresentationFrame result;
        result.width = 2; result.height = 2;
        result.pixels.assign(640u * 512u * 4u, uint8_t(++presentations));
        return result;
    }
    bool ClearFramebuffer(const GSContext&, uint32_t) override { return true; }
    uint32_t ConsumeLocalToHostBytes(uint8_t*, uint32_t) override { return 0; }
    uint32_t ReadVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) const override { return 0; }
    void WriteVram(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t) override {
        if (writeGate) writeGate->wait();
        ++writes;
    }
    void SnapshotVram(std::vector<uint8_t>& out) const override {
        if (snapshotGate) snapshotGate->wait();
        out.assign(16, 0);
    }
    GSTransferSnapshot GetTransferSnapshot() const override { return {}; }
};
struct Fixture {
    std::unique_ptr<GS> gs = std::make_unique<GS>();
    std::unique_ptr<GSRegisters> regs = std::make_unique<GSRegisters>();
    Backend* backend;
    Fixture() {
        gs->init(nullptr, 0, regs.get());
        auto owned = std::make_unique<Backend>(); backend = owned.get();
        gs->setRasterBackend(std::move(owned));
        gs->latchHostPresentationFrame();
    }
    bool pixels(unsigned value) {
        std::vector<uint8_t> data; uint32_t width=0, height=0;
        return gs->copyLatchedHostPresentationFrame(data,width,height) &&
            width==2 && height==2 && data.size()==16 &&
            std::all_of(data.begin(),data.end(),[&](uint8_t pixel){return pixel==value;});
    }
};
bool check(bool value, const char* message) {
    if (!value) std::cerr << message << '\n';
    return value;
}
int main() {
    bool passed = true;
    {
        Fixture f; Gate gate; f.backend->writeGate=&gate;
        auto producer=std::async(std::launch::async,[&]{f.gs->WriteVram(0,0,1,0,0,42);});
        gate.await();
        auto present=std::async(std::launch::async,[&]{f.gs->latchHostPresentationFrame();});
        bool ready=present.wait_for(1s)==std::future_status::ready;
        bool retained=ready && f.pixels(1);
        gate.release.set_value(); producer.get(); present.get();
        passed &= check(ready && retained,"Presentation waited for a busy producer or lost the completed frame");
        f.backend->writeGate=nullptr; f.gs->latchHostPresentationFrame();
        passed &= check(f.pixels(2) && f.backend->writes==1,"Presentation did not resume after the original producer completed");
    }
    {
        Fixture f; Gate gate; f.backend->snapshotGate=&gate;
        auto snapshot=std::async(std::launch::async,[&]{f.gs->refreshDisplaySnapshot();});
        gate.await();
        auto present=std::async(std::launch::async,[&]{f.gs->latchHostPresentationFrame();});
        bool ready=present.wait_for(1s)==std::future_status::ready;
        bool retained=ready && f.pixels(1);
        gate.release.set_value(); snapshot.get(); present.get();
        passed &= check(ready && retained,"Presentation waited for diagnostic readback or lost the completed frame");
        f.backend->snapshotGate=nullptr; f.gs->latchHostPresentationFrame();
        passed &= check(f.pixels(2),"Presentation did not resume after diagnostic readback");
    }
    {
        Fixture f; Gate raster, display; f.backend->writeGate=&raster; f.backend->presentGate=&display;
        auto present=std::async(std::launch::async,[&]{f.gs->latchHostPresentationFrame();});
        display.await();
        auto producer=std::async(std::launch::async,[&]{f.gs->WriteVram(0,0,1,0,0,42);});
        raster.await(); display.release.set_value();
        bool ready=present.wait_for(1s)==std::future_status::ready;
        bool completed=ready && f.pixels(2);
        raster.release.set_value(); producer.get(); present.get();
        passed &= check(ready && completed,"A diagnostic history lock delayed a ready frame");
    }
    if (!passed) return 1;
    std::cout << "Busy producer/readback retains completed pixels; ready frames bypass history contention; presentation resumes\n";
}
