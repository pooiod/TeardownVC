#version 2

local VERSION = 1
local cache = {}
local echoTimer = 0
local ECHO_CALC_INTERVAL = 0.5
local ECHO_SPHERE_RADIUS = 100

local MATERIAL_ECHO_SCORES = {
    ["glass"] = 1,
    ["concrete"] = 3,
    ["rock"] = 5,
    ["grass"] = -5,
    ["plaster"] = -8
}

function updateInt(key, val)
    if cache[key] ~= val then
        SetInt("savegame.mod." .. key, val)
        cache[key] = val
    end
end

function calculateEnvironmentEcho()
    local pos = GetPlayerPos()
    local totalScore = 0
    local radiusSq = ECHO_SPHERE_RADIUS * ECHO_SPHERE_RADIUS
    
    local voxels = QueryVoxels(pos, {ECHO_SPHERE_RADIUS, ECHO_SPHERE_RADIUS, ECHO_SPHERE_RADIUS})
    
    for i=1, #voxels, 4 do
        local vx, vy, vz, matId = voxels[i], voxels[i+1], voxels[i+2], voxels[i+3]
        
        local dx, dy, dz = vx - pos[1], vy - pos[2], vz - pos[3]
        if dx*dx + dy*dy + dz*dz <= radiusSq then
            local mat = GetMaterial(matId)
            
            if MATERIAL_ECHO_SCORES[mat.name] then
                totalScore = totalScore + MATERIAL_ECHO_SCORES[mat.name]
            else
                if mat.hardness < 0.3 then
                    totalScore = totalScore - 2
                elseif mat.hardness < 1.0 then
                    totalScore = totalScore + 1
                else
                    totalScore = totalScore + 2
                end
            end
        end
    end
    
    local echoMs = math.floor(math.max(0, math.min(2000, 50 + totalScore * 0.2)))
    
    if echoMs < 30 then
        echoMs = 0
    end
    
    updateInt("echo", echoMs)
end


function server.init()
    shared.session_id = math.random(1000, 9999)
    shared.user_map = {}
    shared.next_id = 1
	shared.ShowPlayerMap = 0
    -- DebugPrint("VC Server Initialized. Session: " .. shared.session_id)
end

function server.update(dt)
    local clients = Network.GetClients()
    local map = shared.user_map
    local changed = false
    for _, c in ipairs(clients) do
        if not map[c.name] then
            map[c.name] = shared.next_id
            shared.next_id = shared.next_id + 1
            changed = true
            -- DebugPrint("Assigned VC ID " .. map[c.name] .. " to " .. c.name)
        end
    end
    if changed then shared.user_map = map end
end

function client.tick(dt)
    updateInt("version", VERSION)
    if shared.session_id then updateInt("session", shared.session_id) end
    
    local myName = GetUserNickname()
    if shared.user_map and shared.user_map[myName] then updateInt("userid", shared.user_map[myName]) end

    local pos = GetPlayerPos()
    updateInt("pos_x", math.floor(pos[1] * 100))
    updateInt("pos_y", math.floor(pos[2] * 100))
    updateInt("pos_z", math.floor(pos[3] * 100))

    local is_dead = (GetPlayerHealth() <= 0) and 1 or 0
    updateInt("isdead", is_dead)

    local is_owner = 0
    if Network and Network.IsConnected() then
        if Network.GetClients()[1].name == myName then is_owner = 1 end
    else is_owner = 1 end
    updateInt("isowner", is_owner)
    
    updateInt("global", 0)
	updateInt("showmap", shared.ShowPlayerMap)

    -- echoTimer = echoTimer + dt
    -- if echoTimer >= ECHO_CALC_INTERVAL then
    --     echoTimer = 0
    --     calculateEnvironmentEcho()
    -- end
    updateInt("echo", 0)
end
