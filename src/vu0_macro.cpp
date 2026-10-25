// SPDX-License-Identifier: GPL-3.0-or-later
#include "yakuza/vu0_macro.hpp"
#include "ps2_runtime.h"
#include "runtime/ps2_vu1.h"
#include <array>
#include <cstring>
#include <map>
#include <memory>
#include <stdexcept>

namespace yakuza {
namespace {
struct Evaluator {
    VU1Interpreter unit{VU1Interpreter::Unit::VU0};
    std::array<uint32_t,16> program{};
    std::array<uint8_t,16> data{};
    explicit Evaluator(uint32_t instruction) {
        for (unsigned pair=0; pair<8; ++pair) {
            program[pair*2]=0x8000033c; // Lower NOP.
            program[pair*2+1]=0x000002ff; // Upper NOP.
        }
        program[1]=instruction;
        program[11]|=1u<<30; // End after the original flag-latency NOPs and delay slot.
    }
};
}
void vu0UpperWithFlags(R5900Context& context, GS& gs, uint32_t instruction) {
    if (instruction & 0xfe000000u) throw std::runtime_error("VU0 upper evaluator received instruction-control bits");
    // Each immutable program has a separate decoded cache. This evaluator is
    // isolated from guest microprogram memory and the runtime's live VU0 unit.
    thread_local std::map<uint32_t,std::unique_ptr<Evaluator>> evaluators;
    auto& evaluator=evaluators[instruction];
    if (!evaluator) evaluator=std::make_unique<Evaluator>(instruction);
    auto& state=evaluator->unit.state();
    std::memcpy(state.vf,context.vu0_vf,sizeof(state.vf));
    std::memcpy(state.acc,&context.vu0_acc,sizeof(state.acc));
    state.q=context.vu0_q;state.p=context.vu0_p;state.i=context.vu0_i;
    state.mac=context.vu0_mac_flags;state.status=context.vu0_status;state.clip=context.vu0_clip_flags;
    evaluator->unit.execute(reinterpret_cast<uint8_t*>(evaluator->program.data()),
        sizeof(evaluator->program),evaluator->data.data(),evaluator->data.size(),gs,nullptr,0,0,0,32);
    // Keep a guard pair after the delay slot: the interpreter wraps its PC at
    // codeSize, so a buffer ending there would hide the expected stop address.
    if (state.pc!=56u) throw std::runtime_error("VU0 upper evaluator did not finish its verified program");
    std::memcpy(context.vu0_vf,state.vf,sizeof(state.vf));
    std::memcpy(&context.vu0_acc,state.acc,sizeof(state.acc));
    context.vu0_mac_flags=state.mac;context.vu0_status=static_cast<uint16_t>(state.status);
    context.vu0_clip_flags=state.clip;
}
}
