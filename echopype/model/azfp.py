"""
echopype data model inherited from based class EchoData for AZFP data.
"""

import datetime as dt
import numpy as np
import xarray as xr
import os
from .echo_data import EchoData


class EchoDataAZFP(EchoData):
    """Class for manipulating AZFP echo data that is already converted to netCDF."""

    def __init__(self, file_path=""):
        EchoData.__init__(self, file_path)

    def calc_range(self, tilt_corrected=False):
        ds_beam = xr.open_dataset(self.file_path, group='Beam')
        ds_vend = xr.open_dataset(self.file_path, group='Vendor')
        ds_env = xr.open_dataset(self.file_path, group='Environment')

        frequency = ds_beam.frequency
        range_samples = ds_beam.number_of_samples_digitized_per_pings
        pulse_length = ds_beam.transmit_duration_nominal        # Units: seconds
        bins_to_avg = ds_beam.bins_to_avg
        range_bin = ds_beam.range_bin
        sound_speed = ds_env.sound_speed_indicative
        dig_rate = ds_vend.digitization_rate
        lockout_index = ds_vend.lockout_index

        m = []
        for jj in range(len(frequency)):
            m.append(np.arange(1, len(range_bin) - bins_to_avg + 2,
                     bins_to_avg))
        m = xr.DataArray(m, coords=[('frequency', frequency), ('range_bin', range_bin)])
        # m = xr.DataArray(m, coords=[('frequency', Data[0]['frequency'])])         # If range varies in frequency
        # Create DataArrays for broadcasting on dimension frequency

        # TODO Handle varying range
        # Calculate range from soundspeed for each frequency
        depth = (sound_speed * lockout_index[0] / (2 * dig_rate[0]) + sound_speed / 4 *
                 (((2 * m - 1) * range_samples[0] * bins_to_avg - 1) / dig_rate[0] +
                 (pulse_length / np.timedelta64(1, 's')))).drop('ping_time')
        if tilt_corrected:
            depth = ds_beam.cos_tilt_mag.mean() * depth

        return depth

        ds_beam.close()
        ds_vend.close()
        ds_env.close()

    def calibrate(self, save=True):
        """Perform echo-integration to get volume backscattering strength (Sv) from AZFP power data.

        Parameters
        -----------
        save : bool, optional
               whether to save calibrated Sv output
               default to ``True``
        """

        ds_env = xr.open_dataset(self.file_path, group="Environment")
        ds_beam = xr.open_dataset(self.file_path, group="Beam")

        self.sample_thickness = ds_env.sound_speed_indicative * (ds_beam.sample_interval / np.timedelta64(1, 's')) / 2
        depth = self.calc_range()
        self.Sv = (ds_beam.EL - 2.5 / ds_beam.DS + ds_beam.backscatter_r / (26214 * ds_beam.DS) -
                   ds_beam.TVR - 20 * np.log10(ds_beam.VTX) + 20 * np.log10(depth) +
                   2 * ds_beam.sea_abs * depth -
                   10 * np.log10(0.5 * ds_env.sound_speed_indicative *
                                 ds_beam.transmit_duration_nominal.astype('float64') / 1e9 *
                                 ds_beam.equivalent_beam_angle) + ds_beam.Sv_offset)
        if save:
            print("{} saving calibrated Sv to {}".format(dt.datetime.now().strftime('%H:%M:%S'), self.Sv_path))
            self.Sv.to_dataset(name="Sv").to_netcdf(path=self.Sv_path, mode="w")

        # Close opened resources
        ds_env.close()
        ds_beam.close()
        pass

    def calibrate_ts(self, save=True):
        ds_beam = xr.open_dataset(self.file_path, group="Beam")
        depth = self.calc_range()

        self.TS = (ds_beam.EL - 2.5 / ds_beam.DS + ds_beam.backscatter_r / (26214 * ds_beam.DS) -
                   ds_beam.TVR - 20 * np.log10(ds_beam.VTX) + 40 * np.log10(depth) +
                   2 * ds_beam.sea_abs * depth)
        if save:
            print("{} saving calibrated TS to {}".format(dt.datetime.now().strftime('%H:%M:%S'), self.TS_path))
            self.TS.to_dataset(name="TS").to_netcdf(path=self.TS_path, mode="w")

        ds_beam.close()

    def get_MVBS(self):
        with xr.open_dataset(self.file_path, group='Beam') as ds_beam:
            super().get_MVBS('Sv', ds_beam.bins_to_avg, ds_beam.time_to_avg)
        pass
