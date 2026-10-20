// SPDX-License-Identifier: GPL-3.0-or-later
// Diagnostic host for the pinned PS2Recomp IOP subsystem, not a game runner.
#include "ps2x/iop/iop_subsystem.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#endif

using namespace ps2x::iop;

static uint32_t word(std::span<const uint8_t> bytes, size_t offset) {
    if (offset > bytes.size() || bytes.size() - offset < 4) throw std::runtime_error("Truncated IRX bundle table");
    return uint32_t(bytes[offset]) | (uint32_t(bytes[offset + 1]) << 8) |
           (uint32_t(bytes[offset + 2]) << 16) | (uint32_t(bytes[offset + 3]) << 24);
}

static bool isElf(std::span<const uint8_t> bytes) {
    return bytes.size() >= 52 && bytes[0] == 0x7f && bytes[1] == 'E' && bytes[2] == 'L' && bytes[3] == 'F';
}

struct ModuleImage { std::string name; std::span<const uint8_t> bytes; };

static std::vector<ModuleImage> images(std::span<const uint8_t> bytes, const std::string& name) {
    if (isElf(bytes)) return {{name, bytes}};
    const auto groups = word(bytes, 0);
    if (groups == 0 || groups > 16) throw std::runtime_error("Expected an IRX or IRX.DAT bundle");
    size_t previousGroupEnd = 16u + groups * 16u;
    std::vector<ModuleImage> output;
    for (uint32_t group = 0; group < groups; ++group) {
        const size_t table = 16u + group * 16u;
        const size_t start = word(bytes, table), size = word(bytes, table + 4u);
        if (start < previousGroupEnd || start > bytes.size() || size > bytes.size() - start)
            throw std::runtime_error("Invalid IRX.DAT group bounds");
        const auto data = bytes.subspan(start, size);
        const auto count = word(data, 0);
        if (count == 0 || count > 256 || word(data, 4) != word(bytes, table + 12u))
            throw std::runtime_error("Invalid IRX.DAT group metadata");
        size_t previousEnd = 16u + count * 16u;
        if (previousEnd > data.size()) throw std::runtime_error("Truncated IRX.DAT module table");
        for (uint32_t slot = 0; slot < count; ++slot) {
            const size_t record = 16u + slot * 16u;
            const size_t offset = word(data, record), length = word(data, record + 4u);
            if (offset < previousEnd || offset > data.size() || length > data.size() - offset)
                throw std::runtime_error("Invalid IRX.DAT module bounds");
            if (length != 0) {
                const auto image = data.subspan(offset, length);
                if (!isElf(image)) throw std::runtime_error("IRX.DAT entry is not an ELF image");
                output.push_back({name + "#" + std::to_string(group) + ":" + std::to_string(slot), image});
            }
            previousEnd = offset + length;
        }
        previousGroupEnd = start + size;
    }
    if (output.empty()) throw std::runtime_error("IRX bundle contains no modules");
    return output;
}

class ProbeHost final : public IopHost {
public:
    std::vector<uint8_t> guest = std::vector<uint8_t>(32u * 1024u * 1024u);
    bool readGuest(uint32_t address, void* destination, size_t size) const override {
        if ((size && !destination) || address > guest.size() || size > guest.size() - address) return false;
        if (size) std::memcpy(destination, guest.data() + address, size);
        return true;
    }
    bool writeGuest(uint32_t address, const void* source, size_t size) override {
        if ((size && !source) || address > guest.size() || size > guest.size() - address) return false;
        if (size) std::memcpy(guest.data() + address, source, size);
        return true;
    }
    bool zeroGuest(uint32_t address, size_t size) override {
        if (address > guest.size() || size > guest.size() - address) return false;
        if (size) std::memset(guest.data() + address, 0, size);
        return true;
    }
    bool normalizeGuestAddress(uint32_t address, uint32_t& normalized) const override {
        normalized = address & 0x1fffffffu;
        return normalized < guest.size();
    }
    uint32_t allocateIopHandle(IopHandleKind) override { return nextHandle_ += 128u; }
    uint32_t allocateGuest(uint32_t, uint32_t) override { return 0u; }
    void freeGuest(uint32_t) override {}
    void audioCommand(uint32_t, uint32_t, GuestBuffer, GuestBuffer) override {
        std::cerr << "[probe] Audio output is unavailable in this diagnostic host\n";
    }
    std::string hostPath(HostPathKind) const override { return {}; }
    std::string translateGuestPath(std::string_view path) const override { return std::string(path); }
    uint64_t openHostFile(std::string_view) override { return 0u; }
    bool hostFileSize(uint64_t, uint64_t&) const override { return false; }
    bool readHostFile(uint64_t, uint64_t, void*, size_t, size_t& read) override { read = 0; return false; }
    void closeHostFile(uint64_t) override {}
    int32_t memoryCard(const MemoryCardRequest&) override { return -1; }
    bool hasGuestFunction(uint32_t) const override { return false; }
    bool invokeGuestFunction(uint64_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t, uint32_t*) override { return false; }
    void log(LogLevel, std::string_view message) override {
        if (logCount_++ < 200u) std::cerr << message << '\n';
    }
private:
    uint32_t nextHandle_ = 0x1000u;
    unsigned logCount_ = 0;
};

static int run(const std::vector<std::filesystem::path>& arguments) {
    if (arguments.size() == 1 && arguments[0] == "--help") {
        std::cout << "Usage: yakuza_iop_probe <IRX.DAT-or-IRX-file> [more-files ...]\n"
                     "Loads supplied modules in order into a minimal diagnostic host.\n"
                     "No game files are included. Module load success does not verify audio, input or gameplay.\n";
        return 0;
    }
    if (arguments.empty()) { std::cerr << "Supply IRX module files, or --help\n"; return 2; }
    try {
        ProbeHost host;
        IopSubsystem iop(host);
        bool failed = false;
        for (const auto& path : arguments) {
            const auto size = std::filesystem::file_size(path);
            if (size < 52 || size > 8u * 1024u * 1024u) throw std::runtime_error("IRX size outside probe limits");
            std::ifstream input(path, std::ios::binary);
            std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)), {});
            if (!input.eof() && input.fail()) throw std::runtime_error("IRX read failed");
            if (bytes.size() != size) throw std::runtime_error("IRX file could not be read completely");
            const auto utf8Name = path.filename().u8string();
            const std::string name(utf8Name.begin(), utf8Name.end());
            for (const auto& image : images(bytes, name)) {
                if (!host.writeGuest(0x1000u, image.bytes.data(), image.bytes.size()))
                    throw std::runtime_error("IRX could not be copied into diagnostic EE memory");
                const auto result = iop.loadModuleBuffer(0x1000u);
                iop.runEeCycles(100000u);
                const auto snapshot = iop.debugSnapshot();
                const bool resident = result.moduleId > 0 && (result.startResult == 0 || result.startResult == 2);
                failed |= !resident;
                std::cout << image.name << ": module_id=" << result.moduleId
                      << " start_result=" << result.startResult << " resident=" << resident
                      << " loaded=" << snapshot.emulatorLoadedModules
                      << " threads=" << snapshot.emulatorThreads << " rpc_servers=" << snapshot.emulatorRpcServers
                      << " instructions=" << snapshot.emulatorInstructions << '\n';
                for (const auto& diagnostic : snapshot.diagnostics) std::cerr << "[diagnostic] " << diagnostic << '\n';
            }
        }
        return failed ? 1 : 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 2;
    }
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
    SetConsoleOutputCP(CP_UTF8);
    std::vector<std::filesystem::path> arguments;
    for (int index = 1; index < argc; ++index) arguments.emplace_back(argv[index]);
    return run(arguments);
}
#else
int main(int argc, char** argv) {
    std::vector<std::filesystem::path> arguments;
    for (int index = 1; index < argc; ++index) arguments.emplace_back(argv[index]);
    return run(arguments);
}
#endif
