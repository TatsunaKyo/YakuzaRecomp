#pragma once
// Build fixture only. No game instructions or original game data.
#include <cstdint>
struct R5900Context;
class PS2Runtime;
void synthetic_entry(uint8_t*, R5900Context*, PS2Runtime*);
