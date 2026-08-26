#version 2

local VERSION = 3
local cache = {}

local RAYS_PER_FRAME = 10
local MAX_BOUNCES = 6
local RAY_MAX_DIST = 100
local SPEED_OF_SOUND = 343
local LERP_SPEED = 12
local PLAYER_HEIGHT_OFFSET = 1.6
local MIN_BOUNCE_THRESHOLD = 0.45
local MIN_SURFACE_HITS = 2

local CLIENT_URL = "https://github.com/pooiod/TeardownVC/releases"

local ReflectivityMap = {
    metal = 1.35,
    hardmetal = 1.35,
    masonry = 1.15,
    brick = 1.15,
    concrete = 0.9,
    rock = 0.95,
    glass = 0.75,
    plaster = 0.45,
    wood = 0.25,
    plastic = 0.4,
    sand = 0.3,
    dirt = 0.25,
    water = 0.8,
    snow = 0.2,
    mud = 0.3,
    rubber = 0.2,
    cloth = 0.05,
    fabric = 0.05,
    foliage = 0.05,
    leaves = 0.05,
    bush = 0.05,
    tree = 0.15,
    bark = 0.15,
    grass = 0.1,
    carpet = 0.02
}

local SmoothnessMap = {
    metal = 0.95,
    hardmetal = 0.95,
    masonry = 0.7,
    brick = 1.0,
    concrete = 0.5,
    rock = 0.6,
    glass = 1.0,
    plaster = 0.5,
    wood = 0.35,
    plastic = 0.7,
    sand = 0.2,
    dirt = 0.2,
    water = 0.99,
    snow = 0.4,
    mud = 0.3,
    rubber = 0.6,
    cloth = 0.3,
    fabric = 0.3,
    foliage = 0.1,
    leaves = 0.1,
    bush = 0.1,
    tree = 0.2,
    bark = 0.2,
    grass = 0.2,
    carpet = 0.1,
    air = 1.0
}

local AbsorptionMap = {
    metal = 0.01,
    hardmetal = 0.01,
    masonry = 0.03,
    brick = 0.03,
    concrete = 0.03,
    rock = 0.03,
    glass = 0.12,
    plaster = 0.42,
    wood = 0.48,
    plastic = 0.3,
    sand = 0.5,
    dirt = 0.55,
    water = 0.05,
    snow = 0.8,
    mud = 0.6,
    rubber = 0.65,
    cloth = 0.95,
    fabric = 0.95,
    foliage = 0.95,
    leaves = 0.95,
    bush = 0.95,
    tree = 0.8,
    bark = 0.8,
    grass = 0.75,
    carpet = 0.98,
    air = 0.5
}

local IsMetalMap = {
    metal = 1,
    hardmetal = 1
}

local notif_duration = 5
local notif_timer = 0
local notif_active = true
local notif_anim = 0 

local window_open = false
local window_anim = 0
local copied_timer = 0

local global_enabled = false

local my_server_id = 0
local my_temp_key = 0
local next_player_id = 1

local NOTIF_WIDTH = 600
local NOTIF_HEIGHT = 50
local BOX_ASSET = "ui/common/box-solid-6.png"

local current_echo = 0
local smoothed_echo = 0

local trace_data = {
    totalStarts = 0,
    totalCasts = 0,
    totalHits = 0,
    totalHitDistance = 0,
    totalSmoothness = 0,
    totalMetal = 0,
    totalAbsorption = 0
}

function reflectVector(dir, normal)
    local dot = dir[1] * normal[1] + dir[2] * normal[2] + dir[3] * normal[3]
    local factor = -2 * dot
    return Vec(
        dir[1] + factor * normal[1],
        dir[2] + factor * normal[2],
        dir[3] + factor * normal[3]
    )
end

function getRandomUnitVector()
    local theta = math.random() * 2 * math.pi
    local z = math.random() * 2 - 1
    local r = math.sqrt(math.max(0, 1 - z * z))
    return Vec(r * math.cos(theta), r * math.sin(theta), z)
end

function recursiveCast(pos, dir, bounceCount)
    trace_data.totalCasts = trace_data.totalCasts + 1
    local hit, dist, normal, shape = QueryRaycast(pos, dir, RAY_MAX_DIST)

    if hit and dist > 0.3 then
        trace_data.totalHits = trace_data.totalHits + 1
        trace_data.totalHitDistance = trace_data.totalHitDistance + dist

        local hit_pos = Vec(
            pos[1] + dir[1] * dist,
            pos[2] + dir[2] * dist,
            pos[3] + dir[3] * dist
        )

        local mat_type = ""
        if shape and shape ~= 0 and GetShapeMaterialAtPosition then
            mat_type = GetShapeMaterialAtPosition(shape, hit_pos)
        end

        local refl = ReflectivityMap[mat_type] or 0
        local smooth = SmoothnessMap[mat_type] or 0
        local absorp = AbsorptionMap[mat_type] or 0.5

        if IsMetalMap[mat_type] then
            trace_data.totalMetal = trace_data.totalMetal + 1
        end

        trace_data.totalSmoothness = trace_data.totalSmoothness + smooth
        trace_data.totalAbsorption = trace_data.totalAbsorption + absorp

        if bounceCount < MAX_BOUNCES and refl > 0.15 then
            local next_bounce_inc = 1 / math.max(0.3, refl)
            local ref_dir = reflectVector(dir, normal)
            local nudge_pos = Vec(
                hit_pos[1] + ref_dir[1] * 0.05,
                hit_pos[2] + ref_dir[2] * 0.05,
                hit_pos[3] + ref_dir[3] * 0.05
            )
            recursiveCast(nudge_pos, ref_dir, bounceCount + next_bounce_inc)
        end
    end
end

function calculateEcho(pos, dt)
    trace_data.totalStarts = 0
    trace_data.totalCasts = 0
    trace_data.totalHits = 0
    trace_data.totalHitDistance = 0
    trace_data.totalSmoothness = 0
    trace_data.totalMetal = 0
    trace_data.totalAbsorption = 0

    local eye_pos = Vec(pos[1], pos[2] + PLAYER_HEIGHT_OFFSET, pos[3])

    for i = 1, RAYS_PER_FRAME do
        trace_data.totalStarts = trace_data.totalStarts + 1
        local dir = getRandomUnitVector()
        recursiveCast(eye_pos, dir, 0)
    end

    if trace_data.totalStarts == 0 or trace_data.totalHits < MIN_SURFACE_HITS then
        smoothed_echo = smoothed_echo + (0 - smoothed_echo) * math.min(1, dt * LERP_SPEED * 2)
        if smoothed_echo < 1 then smoothed_echo = 0 end
        current_echo = math.floor(smoothed_echo)
        return current_echo
    end

    local avg_bounces = trace_data.totalHits / trace_data.totalStarts
    local avg_distance = trace_data.totalHitDistance / trace_data.totalHits
    local avg_absorption = trace_data.totalAbsorption / trace_data.totalHits

    if avg_bounces < MIN_BOUNCE_THRESHOLD or avg_absorption > 0.85 then
        smoothed_echo = smoothed_echo + (0 - smoothed_echo) * math.min(1, dt * LERP_SPEED * 2)
        if smoothed_echo < 1 then smoothed_echo = 0 end
        current_echo = math.floor(smoothed_echo)
        return current_echo
    end

    local enclosure_energy = math.max(0, (avg_bounces - MIN_BOUNCE_THRESHOLD) / 1.6)
    local material_reflectivity = math.max(0, 1 - (avg_absorption * 1.15))
    local acoustic_power = math.min(1.4, enclosure_energy * material_reflectivity)

    if acoustic_power <= 0.05 then
        smoothed_echo = smoothed_echo + (0 - smoothed_echo) * math.min(1, dt * LERP_SPEED * 2)
        if smoothed_echo < 1 then smoothed_echo = 0 end
        current_echo = math.floor(smoothed_echo)
        return current_echo
    end

    local raw_ms = (2 * avg_distance / SPEED_OF_SOUND) * 1000 * acoustic_power
    local target_ms = math.floor(raw_ms)

    if target_ms < 6 then
        target_ms = 0
    end

    smoothed_echo = smoothed_echo + (target_ms - smoothed_echo) * math.min(1, dt * LERP_SPEED)
    if smoothed_echo < 1 then smoothed_echo = 0 end
    current_echo = math.floor(smoothed_echo + 0.5)
    return current_echo
end

function updateInt(key, val, force)
    if force or cache[key] ~= val then
        SetInt("savegame.mod." .. key, val)
        cache[key] = val
    end
end

function server.init()
    if GetTime then
        math.randomseed(math.floor(GetTime() * 1000))
    end
    shared.id_requests = {}
    shared.id_responses = {}
    shared.user_map = {}
    shared.ShowPlayerMap = 0
    shared.session_id = math.random(1000, 9999)
end

function server.update(dt)
    if not shared.session_id then
        shared.session_id = math.random(1000, 9999)
    end

    if shared.id_requests and #shared.id_requests > 0 then
        for i, request in ipairs(shared.id_requests) do
            if not shared.id_responses[request.temp_key] then
                local assigned_id = next_player_id
                shared.id_responses[request.temp_key] = assigned_id
                shared.user_map[assigned_id] = {name = request.name}
                next_player_id = next_player_id + 1
            end
        end
        shared.id_requests = {}
    end
end

function client.tick(dt)
    if Network and Network.IsConnected() then
        if my_server_id == 0 then
            if my_temp_key == 0 then
                my_temp_key = math.random(1000000, 9999999)
                if not shared.id_requests then shared.id_requests = {} end
                
                table.insert(shared.id_requests, {temp_key = my_temp_key, name = GetUserNickname()})
            end

            if shared.id_responses and shared.id_responses[my_temp_key] then
                my_server_id = shared.id_responses[my_temp_key]
            end
        end
    end

    updateInt("version", VERSION)
    updateInt("session", shared.session_id, true)
    updateInt("userid", my_server_id)

    local pos = GetPlayerPos()
    updateInt("pos_x", math.floor(pos[1] * 100))
    updateInt("pos_y", math.floor(pos[2] * 100))
    updateInt("pos_z", math.floor(pos[3] * 100))
    updateInt("isdead", (GetPlayerHealth() <= 0) and 1 or 0)

    local is_owner = 1
    if Network and Network.IsConnected() then
        if Network.GetClients()[1].name ~= GetUserNickname() then is_owner = 0 end
    end
    updateInt("isowner", is_owner)

    updateInt("global", global_enabled and 1 or 0)
    updateInt("showmap", shared.ShowPlayerMap or 0)
    
    local echo_val = calculateEcho(pos, dt)
    updateInt("echo", echo_val)

    if copied_timer > 0 then
        copied_timer = math.max(0, copied_timer - dt)
    end

    if notif_active and not window_open then
        notif_timer = notif_timer + dt
        if notif_timer > notif_duration then
            notif_active = false
        end
        if InputPressed("return") or InputPressed("enter") then
            window_open = true
            notif_active = false
        end
    end

    local button_text = "Global Voice: " .. (global_enabled and "ON" or "OFF")
    if PauseMenuButton(button_text) then
        global_enabled = not global_enabled
    end
end

function drawRoundedRect(w, h, r, g, b, a)
    UiColor(r, g, b, a)
    UiImageBox(BOX_ASSET, w, h, 6, 6) 
end

function client.draw(dt)
    local anim_speed = 5

    local notif_target = (notif_active and not window_open) and 1 or 0
    notif_anim = notif_anim + (notif_target - notif_anim) * dt * anim_speed

    local window_target = window_open and 1 or 0
    window_anim = window_anim + (window_target - window_anim) * dt * anim_speed

    if notif_anim > 0.01 then
        UiPush()
            local t = 1 - math.pow(1 - notif_anim, 3)
            local start_x = -NOTIF_WIDTH - 50
            local end_x = 30
            local cur_x = start_x + (end_x - start_x) * t

            UiTranslate(cur_x, 30)
            drawRoundedRect(NOTIF_WIDTH, NOTIF_HEIGHT, 0.1, 0.1, 0.1, 0.95)

            UiPush()
                UiTranslate(20, NOTIF_HEIGHT / 2)
                UiAlign("left middle")
                UiFont("bold.ttf", 20)
                UiColor(1, 1, 1, 1)
                UiText("This server is using TeardownVC, Press Enter to download the TDVC client")
            UiPop()
        UiPop()
    end

    if window_anim > 0.01 then
        UiMakeInteractive()
        UiPush()
            local alpha = window_anim

            UiColor(0, 0, 0, 0.6 * alpha)
            UiRect(UiWidth(), UiHeight())

            local w, h = 500, 250
            UiTranslate(UiCenter(), UiMiddle())
            UiTranslate(-w/2, -h/2)

            drawRoundedRect(w, h, 0.15, 0.15, 0.15, alpha)

            UiPush()
                drawRoundedRect(w, 50, 0.1, 0.1, 0.1, alpha)
                UiTranslate(w/2, 25)
                UiAlign("center middle")
                UiFont("bold.ttf", 22)
                UiColor(1, 1, 1, alpha)
                UiText("TeardownVC Client")
            UiPop()

            UiPush()
                UiTranslate(w/2, 80)
                UiAlign("center middle")
                UiFont("regular.ttf", 20)
                UiColor(0.9, 0.9, 0.9, alpha)
                UiText("An external client is required for voice chat.")
                UiTranslate(0, 30)
                UiText("Please download the latest version from the GitHub releases.")

                UiTranslate(0, 40)
                local link_w = 440
                local link_h = 32
                UiPush()
                    UiTranslate(-link_w/2, -link_h/2)
                    local link_hover = UiIsMouseInRect(link_w, link_h)
                    if link_hover and InputPressed("lmb") then
                        copied_timer = 2.5
                        if SetClipboardText then
                            SetClipboardText(CLIENT_URL)
                        end
                        if Command then
                            Command("game.openurl " .. CLIENT_URL)
                        end
                    end
                UiPop()

                if copied_timer > 0 then
                    -- UiFont("bold.ttf", 20)
                    -- UiColor(0.3, 1, 0.4, alpha)
                    -- UiText("")
                else
                    local link = "[[https://github.com/pooiod/TeardownVC/releases;label=github.com/pooiod/TeardownVC/releases;color=#4488FF;underline=true]]"
                    UiFont("bold.ttf", 24)
                    UiText(link)
                end
            UiPop()

            UiPush()
                local bw, bh = 150, 40
                local bx = (w - bw) / 2
                local by = h - bh - 20
                UiTranslate(bx, by)

                local hover = UiIsMouseInRect(bw, bh)
                if hover and InputPressed("lmb") then
                    window_open = false
                end

                local buttonColor = hover and 0.35 or 0.25
                drawRoundedRect(bw, bh, buttonColor, buttonColor, buttonColor, alpha)

                UiTranslate(bw/2, bh/2)
                UiAlign("center middle")
                UiFont("bold.ttf", 18)
                UiColor(1, 1, 1, alpha)
                UiText("Close")
            UiPop()
        UiPop()
    end
end
