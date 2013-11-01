/* *************************************************************
 *  
 *   Active Particles on Curved Spaces (APCS)
 *   
 *   Author: Rastko Sknepnek
 *  
 *   Division of Physics
 *   School of Engineering, Physics and Mathematics
 *   University of Dundee
 *   
 *   (c) 2013
 *   
 *   This program cannot be used, copied, or modified without
 *   explicit permission of the author.
 * 
 * ************************************************************* */

/*!
 * \file pair_lj_potential.cpp
 * \author Rastko Sknepnek, sknepnek@gmail.com
 * \date 22-Oct-2013
 * \brief Implementation of PairLJPotential class
 */ 

#include "pair_lj_potential.hpp"

void PairLJPotential::compute()
{
  int N = m_system->size();
  bool periodic = m_system->get_periodic();
  BoxPtr box = m_system->get_box();
  double sigma = m_sigma;
  double eps = m_eps;
  double rcut = m_rcu;
  double sigma_sq = sigma*sigma, rcut_sq = rcut*rcut;
 
  // Reset total potential energy to zero
  m_potential_energy = 0.0;
  for  (int i = 0; i < N; i++)
  {
    Particle& pi = m_system->get_particle(i);
    vector<int>& neigh = m_nlist->get_neighbours(i);
    for (j = 0; j < neigh.size(); j++)
    {
      Particle& pj = m_system->get_particle(neigh[j]);
      if (m_has_pair_params)
      {
        rcut = m_pair_params[make_pair(pi.get_type(),pj.get_type())]["rcut"];
        rcut_sq = rcut*rcut;
      }
      double dx = pj.x - pi.x, dy = pj.y - pi.y, dz = pj.z - pi.z;
      if (periodic)
      {
        if (dx > box->xhi) dx -= box->Lx;
        else if (dx < box->xlo) dx += box->Lx;
        if (dy > box->yhi) dy -= box->Ly;
        else if (dy < box->ylo) dy += box->Ly;
        if (dz > box->zhi) dz -= box->Lz;
        else if (dz < box->zlo) dz += box->Lz;
      }
      double r_sq = dx*dx + dy*dy + dz*dz;
      if (r_sq <= rcut_sq)
      {
        if (m_has_pair_params)
        {
          sigma = m_pair_params[make_pair(pi.get_type(),pj.get_type())]["sigma"];
          eps = m_pair_params[make_pair(pi.get_type(),pj.get_type())]["epsilon"];
          sigma_sq = sigma*sigma;
        }
        double inv_r_sq = sigma_sq/r_sq;
        double inv_r_6  = inv_r_sq*inv_r_sq*inv_r_sq;
        // Handle potential 
        m_potential_energy += 4.0*eps*inv_r_6*(inv_r_6 - 1.0);
        if (m_shifted)
        {
          double inv_r_cut_sq = sigma_sq/rcut_sq;
          double inv_r_cut_6 = inv_r_cut_sq*inv_r_cut_sq*inv_r_cut_sq;
          m_potential_energy -= 4.0 * epsilon * inv_r_cut_6 * (inv_r_cut_6 - 1.0);
        }
        // Handle force
        double force_factor = 48.0*epsilon*inv_r_6*(inv_r_6 - 0.5)*inv_r_sq;
        pi.fx += force_factor*dx;
        pi.fy += force_factor*dy;
        pi.fz += force_factor*dz;
        // Use 3d Newton's law
        pj.fx -= force_factor*dx;
        pj.fy -= force_factor*dy;
        pj.fz -= force_factor*dz;
      }
    }
  }
}