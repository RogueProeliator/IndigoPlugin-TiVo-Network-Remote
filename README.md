# Introduction
This Indigo 6.1+ plugin allows Indigo to act as a remote control for a network-connected TiVo Digital Video Recorder. Virtually every command/button found on the standard remote can be sent to TiVo as well as several additional commands not found on the TiVo-branded remote.

The only limitation of this TiVo-provided interface is that connected applications are simply acting as a remote and get little feedback, limited primarily to the current channel (as shown on Live TV).

_**INDIGO 6 IMPORTANT NOTE:**_ The Indigo 6 version of this plugin is end-of-life with respect to new development, however the latest stable version on Indigo 6 is [still available](https://github.com/RogueProeliator/IndigoPlugin-TiVo-Network-Remote/releases/tag/v1.4.19) and is working as expected at the moment. Please consider an upgrade to Indigo 7 to support further development of our favorite HA platform!

# Hardware Requirements
This plugin should work with any network-connected TiVo which supports the TiVo TCP Control Protocol; generally speaking this means any Series 3 or Premier (or newer) DVR which is running at least v9.4 of the TiVo software. This plugin has been successfully tested with:

- TiVo Series 3
- TiVo Premier
- TiVo Mini
- TiVo Bolt
- TiVo Roamio

The auto-discovery feature requires that the TiVo and Indigo be on the same subnet, though manual IP entry should allow remote control via a WAN interfaces (such as over a VPN connection). You may also want to consider setting a static IP address on the TiVo to help ensure a stable connection (see below).

# Enabling Network Remote Control in the TiVo Software - *Important Requirement*
Before any device (not just this plugin) may initiate network control over a TiVo, this feature must be enabled on the TiVo DVR itself. To enable remote control on your TiVo DVR:
1. Go to TiVo Central -> Messages & Settings -> Settings -> Remote, CableCARD & Devices -> Network Remote Control
2. Choose Enabled
3. Press Select

# Setting a Static IP Address in the TiVo Software - *Optional*
The TiVo Network Remote plugin communicates with the TiVo DVR using an IP address; if this address changes for any reason then you will need to go to the Device Configuration and change the IP address. To avoid this, you might consider setting your TiVo to a static IP address.

Note that this is optional; I personally have one TiVo that is NOT set with a static IP that has had no trouble keeping its IP lease for several months running while using this plugin.

# Installation and Configuration
### Obtaining the Plugin
The latest released version of the plugin is available for download in the Releases section... those versions in beta will be marked as a Pre-Release and will not appear in update notifications.

### Configuring the Plugin
Upon first installation you will be asked to configure the plugin; please see the instructions on the configuration screen for more information. Most users will be fine with the defaults unless an email is desired when a new version is released.<br />
![](<Documentation/Doc-Images/PluginConfigurationScreen.png>)

# Plugin Devices
Each TiVo that you wish to control should be created as an Indigo Device; In the Device Settings you will need to select from the list of TiVo devices found on the network or else manually enter your TiVo's IP address. Note that if you ever lose connection with your TiVo device, you may need to return here to find/enter the IP Address again if it has picked up a new address on the network. You can avoid this by setting up a static IP address for your TiVo.<br />
![](<Documentation/Doc-Images/EditDeviceSettings.png>)

# Available Actions
### IR Command
This action will send a network command that is equivalent to pressing the button on the remote.

### Teleport
Teleport commands are meant to allow navigation straight to a particular TiVo section/feature. According to the documentation, the teleport command is guaranteed to succeed unless the DVR is in the process of Guided Setup.

### Tune to Channel
This command will tune the TiVo to the requested channel; the DVR must be in Live TV mode in order for the set channel command to succeed. The command may fail if a recording is in progress unless you click the option to force the change.

### Channel Selector Actions
The "channel selector" methods are present as a convenience for you when creating control pages. The channel selector acts as a placeholder for the user entering a channel via a number-pad style interface. Digits may be added (or removed) by buttons on the number page until the user presses a "Go" button at which time you should execute the Tune to Channel Selector action; this will also clear the selector to allow for new input.

# Available Device States
The majority of the TiVo API is for control, but a couple of states are exposed via the plugin:
- **isConnected** & **connectionState** - tracks if Indigo has been able to successfully create/maintain a connection to the TiVo
- **currentChannel** - tracks the current channel in the LiveTV view
- **channelSelector** - stores the current channel selector (see actions above for usage)