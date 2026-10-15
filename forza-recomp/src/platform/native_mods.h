#pragma once
#include <cstdint>
#include <functional>

namespace forza::mods {
void Initialize(std::function<void(bool, float)> presentation);
void Resize(uint32_t width, uint32_t height);
void Frame();
double Projection(uint32_t view, uint32_t width, uint32_t height, double aspect);
}
