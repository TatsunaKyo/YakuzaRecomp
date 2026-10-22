// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <stdexcept>
namespace yakuza {
// Native device failures must not be translated into guest address exceptions.
class NativeDeviceError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
}
