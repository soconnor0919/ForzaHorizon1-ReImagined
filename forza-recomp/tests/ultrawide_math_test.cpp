#include "../src/platform/ultrawide_math.h"
#include <cassert>
#include <cmath>
using namespace forza::ultrawide;
static bool Near(double a, double b) { return std::abs(a-b) < 1e-6; }
int main() {
  auto native = ComputeLayout(2560,1440,100,100,0,0);
  assert(Near(native.aspect_scale,1) && Near(native.hud_scale_x,1));
  auto wide = ComputeLayout(3440,1440,100,100,0,0);
  assert(Near(wide.aspect_scale,3440.0/2560));
  // A centered HUD spans the original 2560 pixels, with circular gauges intact.
  assert(Near(wide.hud_scale_x*3440,2560));
  auto safe = ComputeLayout(3440,1440,90,95,5,4);
  assert(Near(safe.hud_scale_y,.9) && Near(safe.hud_scale_x*3440,2304));
  assert(Near(safe.hud_offset_x,.1) && Near(safe.hud_offset_y,.08));
  auto clamped = ComputeLayout(5120,1440,50,50,1000,-1000);
  assert(clamped.hud_scale_x + clamped.hud_offset_x <= 1.0);
  assert(clamped.hud_scale_y - clamped.hud_offset_y <= 1.0);
  auto empty = ComputeLayout(0,0,100,100,0,0);
  assert(Near(empty.aspect_scale,1));
  assert(GameplayLayoutActive(1.5,false,100,99,0));
  assert(!GameplayLayoutActive(1.5,false,100,95,0));
  assert(GameplayLayoutActive(1.5,true,100,80,0));
  assert(!GameplayLayoutActive(1.5,true,100,60,0));
  assert(!GameplayLayoutActive(1.5,true,100,100,99)); // Map wins over the background world.
  assert(GameplayLayoutActive(1.0,true,100,100,0)); // HUD adjustment also works at 16:9.
  assert(RenderScale(3440,1280,2)==3 && RenderScale(1440,720,2)==2);
  assert(RenderScale(5120,1280,2)==4 && RenderScale(3840,1280,4)==4);
  assert(RenderScale(16384,1280,1)==7);
}
