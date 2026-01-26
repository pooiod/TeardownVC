#version 2

local VERSION = 1
local cache = {}

local notif_duration = 5.0
local notif_timer = 0.0
local notif_active = true
local notif_anim = 0.0 

local window_open = false
local window_anim = 0.0

local global_enabled = false
local myId = 0 

local NOTIF_WIDTH = 600
local NOTIF_HEIGHT = 50
local BOX_ASSET = "ui/common/box-solid-6.png"

function updateInt(key, val, force)
    if force or cache[key] ~= val then
        SetInt("savegame.mod." .. key, val)
        cache[key] = val
    end
end

function server.init()
    math.randomseed(os.time())
    shared.user_map = {}
    shared.client_ids_pending = {}
    shared.ShowPlayerMap = 0
    shared.session_id = math.random(1000, 9999)
end

function server.update(dt)
    if not shared.client_ids_pending then return end

    local map_changed = false
    for key, id in pairs(shared.client_ids_pending) do
        if id and id > 0 and not shared.user_map[key] then
            shared.user_map[key] = id
            map_changed = true
        end
    end
    if map_changed then
        shared.user_map = shared.user_map 
    end
end

function client.tick(dt)
    if myId == 0 then
        myId = math.random(100, 999)
    end

    if Network and Network.IsConnected() then
        if not shared.client_ids_pending then shared.client_ids_pending = {} end
        local myName = GetUserNickname()
        local uniqueKey = myName .. "_" .. tostring(GetPlayer())
        if not shared.client_ids_pending[uniqueKey] then
            shared.client_ids_pending[uniqueKey] = myId
        end
    end

    updateInt("version", VERSION)
    updateInt("session", shared.session_id or 0)
    updateInt("userid", myId)

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
    updateInt("echo", 0)

    if notif_active and not window_open then
        notif_timer = notif_timer + dt
        if notif_timer > notif_duration then
            notif_active = false
        end
        if InputPressed("return") then
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
    local anim_speed = 5.0

    local notif_target = (notif_active and not window_open) and 1.0 or 0.0
    notif_anim = notif_anim + (notif_target - notif_anim) * dt * anim_speed

    local window_target = window_open and 1.0 or 0.0
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
                local link = "[[https://github.com/pooiod/TeardownVC/releases;label=github.com/pooiod/TeardownVC/releases;color=#4488FF;underline=true]]"
                UiFont("bold.ttf", 24)
                UiText(link)
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
