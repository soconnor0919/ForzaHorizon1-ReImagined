// Aspect and view-state strategy adapted from Pinyon Shift contributors.
// SPDX-License-Identifier: BSD-3-Clause (see LICENSE).
#include "forza_mod.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

namespace {
constexpr double native_aspect = 16.0 / 9.0;
std::atomic<uint64_t> frame_number{}, gameplay_frame{}, map_frame{};
std::atomic<double> scale{1.0};
std::atomic<bool> wide{};
bool center_hud = true, protect_menus = true;
const ForzaModHost* host;
std::atomic<bool> projection_logged{};

bool Setting(const std::filesystem::path& path, const char* key) {
  std::ifstream input(path);
  std::string line, section;
  while (std::getline(input, line)) {
    line.erase(std::remove_if(line.begin(), line.end(), [](char c) {
      return c == ' ' || c == '\t' || c == '\r';
    }), line.end());
    if (!line.empty() && line.front() == '[') section = line;
    const auto equal = line.find('=');
    if (section == "[Ultrawide]" && line.substr(0, equal) == key && equal != std::string::npos) {
      const auto value = line.substr(equal + 1);
      return value != "0" && value != "false";
    }
  }
  return true;
}

void Frame(const ForzaModFrame* event, ForzaModPresentation* result) {
  frame_number.store(event->number, std::memory_order_relaxed);
  const auto game = gameplay_frame.load(std::memory_order_relaxed);
  const auto map = map_frame.load(std::memory_order_relaxed);
  const bool game_recent = game && event->number - game <= 2;
  const bool map_recent = map && event->number - map <= 3;
  const bool game_gone = !game || event->number - game > 30;
  const bool was_wide = wide.load(std::memory_order_relaxed);
  const double ratio = event->output_width && event->output_height ?
      double(event->output_width) / event->output_height : native_aspect;
  const double factor = std::clamp(ratio / native_aspect, 1.0, 4.0);
  const bool now_wide = factor > 1.0 && (!protect_menus || (was_wide ?
      !(game_gone || (map_recent && event->number - game > 3)) : game_recent));
  scale.store(factor, std::memory_order_relaxed);
  wide.store(now_wide, std::memory_order_relaxed);
  result->flags = FORZA_MOD_PRESENTATION;
  result->letterbox = !now_wide;
  result->hud_horizontal_scale = float(now_wide && center_hud ? factor : 1.0);
  if (was_wide != now_wide) {
    host->log(now_wide ? "Ultrawide: gameplay framing" : "Ultrawide: protected 16:9 framing");
  }
}

void Projection(ForzaModProjection* event) {
  if (event->viewport_width != 1280 || event->viewport_height != 720) return;
  const auto frame = frame_number.load(std::memory_order_relaxed);
  if (event->view == FORZA_VIEW_GAMEPLAY) gameplay_frame.store(frame, std::memory_order_relaxed);
  if (event->view == FORZA_VIEW_MAP) {
    map_frame.store(frame, std::memory_order_relaxed);
    return;
  }
  // All main-view aspect queries must agree: the game uses them for both
  // projection and culling. Reflections and thumbnails have other sizes; the
  // map is excluded above, and non-gameplay screens restore 16:9 in Frame.
  if (wide.load(std::memory_order_relaxed)) {
    const double original = event->aspect;
    event->aspect *= scale.load(std::memory_order_relaxed);
    if (!projection_logged.exchange(true)) {
      char message[160];
      std::snprintf(message, sizeof(message), "Ultrawide: gameplay projection %.6f -> %.6f",
                    original, event->aspect);
      host->log(message);
    }
  }
}
const ForzaMod mod{sizeof(ForzaMod), FORZA_MOD_ABI, "Ultrawide", Frame, Projection};
}

#ifdef _WIN32
#define MOD_EXPORT __declspec(dllexport)
#else
#define MOD_EXPORT __attribute__((visibility("default")))
#endif
extern "C" MOD_EXPORT const ForzaMod* ForzaModInit(const ForzaModHost* api, const char* directory) {
  if (!api || api->size != sizeof(ForzaModHost) || api->abi != FORZA_MOD_ABI || !api->log) return nullptr;
  if (!(api->capabilities & FORZA_MOD_HUD_SCALE)) {
    api->log("Ultrawide requires the HUD graphics patch; leaving the original presentation unchanged.");
    return nullptr;
  }
  host = api;
  frame_number = gameplay_frame = map_frame = 0;
  scale = 1.0;
  wide = false;
  projection_logged = false;
  const auto config = std::filesystem::u8path(directory) / "ultrawide.ini";
  center_hud = Setting(config, "CenterHud");
  protect_menus = Setting(config, "ProtectMenus");
  api->log("Ultrawide initialized: aspect follows output size; NVIDIA libraries are not used.");
  return &mod;
}
